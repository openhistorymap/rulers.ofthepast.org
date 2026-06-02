"""Augment the curated spine with a balanced pull of world rulers from Wikidata.

The hand-curated table in build_seed.py is the recognisable *core* (~250). To
reach a fuller atlas (500–750) we top it up from Wikidata: every holder of a
monarch-class position (P39 / subclass of Q116 "monarch") whose reign start is
recorded (P580), who has an English Wikipedia article, sliced by century so the
queries stay small and fast.

Each ruler is placed in one of our ten regions by the *label* of the position's
country (P17) or the person's citizenship (P27) — keyword-matched, so historical
states ("Kingdom of France", "Joseon", "Abbasid Caliphate") land correctly. We
drop clergy / consort / titular / pretender positions and mythically-long reigns,
de-duplicate against the curated core by QID, and keep the best-known per region
(ranked by number of Wikipedias) up to a per-region target.

The result is written to harvester/data/seed.json — the same spine the harvester
reads. Curated entries keep their hand-written realms, blurbs, and Civ-wiki links;
augmented entries carry their Wikidata position as the realm and are enriched
(bio, portrait, dates) by the normal harvest.

Run (needs network — WDQS):  python -m harvester.augment_seed
"""

import time
from collections import defaultdict

from . import build_seed as bs
from . import wikidata as wd
from . import wikipedia as wp

# Per-region targets for the *total* roster (curated + augmented). The augmenter
# tops each region up to its target with the best-known Wikidata rulers.
TARGETS = {
    "rome-byzantium": 56,
    "italy": 56,
    "germany": 84,
    "europe-west": 100,
    "europe-east": 86,
    "middle-east": 88,
    "steppe": 26,
    "south-asia": 60,
    "southeast-asia": 36,
    "east-asia": 90,
    "africa": 56,
    "north-america": 66,
    "south-america": 64,
}

# American republics — the head-of-state (Q48352) query runs over these so the
# Americas reach the present, not just the pre-Columbian past.
AMERICAN_COUNTRIES = [
    "Q30", "Q96", "Q155", "Q414", "Q739", "Q717", "Q419", "Q298", "Q750",
    "Q736", "Q733", "Q77", "Q241", "Q790", "Q786", "Q774", "Q783", "Q811",
    "Q800", "Q804", "Q792",
]

# European republics — a president (Q30461) query runs over these (so we get the
# republics' presidents without re-pulling every European monarch). Each routes
# to its lane by country label: France/Portugal/Ireland/Finland/Iceland/Spain/
# Switzerland -> europe-west; Germany/Austria -> germany; Italy -> italy; Greece
# -> rome-byzantium; Turkey -> middle-east; the rest -> europe-east.
EUROPEAN_COUNTRIES = [
    "Q142", "Q183", "Q38", "Q159", "Q36", "Q45", "Q27", "Q40", "Q33", "Q41",
    "Q43", "Q212", "Q218", "Q219", "Q28", "Q213", "Q33946", "Q36704", "Q403",
    "Q224", "Q37", "Q211", "Q191", "Q189", "Q29", "Q39", "Q15180", "Q230",
    "Q399", "Q222",
]

# Century-ish slices over the named-ruler range. Kept small where history is
# dense (medieval / early-modern Europe) so each WDQS query stays well under the
# timeout.
SLICES = [
    (-3300, -500), (-500, 1), (1, 400), (400, 700), (700, 1000),
    (1000, 1200), (1200, 1350), (1350, 1500),
    (1500, 1600), (1600, 1700), (1700, 1801),
    (1801, 1900), (1900, 2030),
]

MAX_REIGN = 80          # drop mythically long "reigns" (data errors / legends)
MAX_START = 2030        # the timeline reaches the present
PRESENT = 2026          # ongoing terms (no recorded end) run to here

# Position / title words that are not the sovereigns this atlas is about.
EXCLUDE_WORDS = (
    "bishop", "archbishop", "patriarch", "pope", "cardinal", "abbot", "abbess",
    "consort", "titular", "pretender", "antipope", "claimant", "co-prince",
    "viceroy", "governor",
    # sub-national heads of government — keep national PMs/chancellors, drop the
    # mayors and state premiers a politician held on the way up.
    "mayor", "burgomaster", "minister-president", "minister president",
    "podestà", "podesta", "alderman", "prefect",
    "nagid", "exilarch", "rabbi", "high priest", "prophet", "saint",
    "deity", "god ", "goddess", "mytholog",
)

# Region keyword rules — ordered; first substring found in a label wins. Tuned so
# "Holy Roman" beats "Roman", and historical state names route correctly.
REGION_RULES = [
    # rome-byzantium (the Greco-Roman Mediterranean). "holy roman" is special-
    # cased to germany in classify() before any of these run.
    ("rome-byzantium", ["byzan", "eastern roman", "western roman", "roman empire",
                        "roman emperor", "roman republic", "latin empire", "nicaea",
                        "trebizond", "thessalonica", "macedon", "epirus", "achaea",
                        "syracuse", "magna graecia", "hellenistic greece", "greece",
                        "greek", "athens", "sparta"]),
    ("italy", ["italy", "italian", "lombard", "ostrogoth", "naples", "neapolitan",
               "two sicilies", "sicily", "sardinia", "savoy", "piedmont", "milan",
               "milanese", "florence", "florentine", "tuscany", "venice", "venetian",
               "genoa", "genoese", "papal", "vatican", "modena", "parma", "mantua",
               "ferrara", "montferrat", "salerno", "amalfi", "romagna", "urbino"]),
    ("germany", ["holy roman", "germany", "german", "prussia", "prussian",
                 "brandenburg", "bavaria", "bavarian", "saxony", "saxon", "swabia",
                 "franconia", "palatinate", "württemberg", "wurttemberg", "hanover",
                 "hesse", "baden", "austria", "austrian", "habsburg", "styria",
                 "tyrol", "salzburg", "cologne", "mainz", "trier", "westphalia",
                 "mecklenburg", "holstein", "oldenburg", "nassau", "frisia"]),
    ("europe-west", ["france", "french", "england", "english", "britain", "british",
                     "scotland", "scottish", "wales", "welsh", "ireland", "irish",
                     "spain", "spanish", "castile", "aragon", "leon", "navarre",
                     "asturias", "galicia", "portugal", "portuguese", "netherlands",
                     "holland", "dutch", "flanders", "brabant", "luxembourg",
                     "belgium", "denmark", "danish", "norway", "norwegian", "sweden",
                     "swedish", "iceland", "switzerland", "swiss", "andorra",
                     "monaco", "malta", "burgundy", "lorraine", "brittany",
                     "normandy", "aquitaine", "frankish", "franks", "visigoth",
                     "finland", "finnish"]),
    ("europe-east", ["russia", "russian", "muscovy", "muscovite", "kievan", "kyiv",
                     "kiev", "rus'", "rus ", " rus", "novgorod", "vladimir-suzdal",
                     "poland", "polish", "lithuania", "lithuanian", "hungary",
                     "hungarian", "bohemia", "bohemian", "czech", "moravia",
                     "serbia", "serbian", "bulgaria", "bulgarian", "croatia",
                     "croatian", "romania", "wallachia", "moldavia", "transylvania",
                     "ukraine", "ukrainian", "belarus", "georgia", "georgian",
                     "armenia", "armenian", "montenegro", "bosnia", "albania",
                     "kievan rus", "galicia-volhynia", "ruthenia", "pomerania",
                     "silesia", "slovakia", "slovenia", "yugoslavia", "latvia",
                     "latvian", "estonia", "estonian", "soviet", "czechoslovakia"]),
    ("middle-east", ["persia", "persian", "iran", "iranian", "achaemenid", "sasanian",
                     "sassanid", "parthian", "media", "elam", "seleucid", "ottoman",
                     "turkey", "turkish", "rûm", "rum sultanate", "caliphate",
                     "umayyad", "abbasid", "rashidun", "arab", "arabia", "iraq",
                     "syria", "babylon", "assyria", "akkad", "sumer", "mesopotamia",
                     "israel", "judah", "judea", "hebrew", "jerusalem", "phoenicia",
                     "hittite", "anatolia", "pergamon", "pontus", "bithynia",
                     "cappadocia", "commagene", "lydia", "phrygia", "urartu",
                     "safavid", "afsharid", "zand", "qajar", "seljuk", "ayyubid",
                     "ghaznavid", "ghurid", "khwarazm", "buyid", "samanid",
                     "fatimid", "ilkhanate", "aq qoyunlu", "qara qoyunlu",
                     "lebanon", "yemen", "oman", "hejaz", "nabatae", "palmyra",
                     "córdoba", "cordoba", "al-andalus", "emirate of"]),
    ("steppe", ["mongol", "mongolia", "hun", "hunnic", "xiongnu", "turkic",
                "khaganate", "khanate", "golden horde", "timurid", "samarkand",
                "kazakh", "scythian", "sarmatian", "göktürk", "gokturk", "uyghur",
                "uighur", "khazar", "avar", "cuman", "kipchak", "oirat", "dzungar",
                "transoxiana", "khwarezm", "bukhara", "khiva", "kokand", "tatars",
                "crimean khanate", "kazan", "astrakhan", "sogdia"]),
    ("south-asia", ["india", "indian", "maurya", "gupta", "mughal", "delhi sultanate",
                    "chola", "vijayanagara", "maratha", "rajput", "mysore", "bengal",
                    "deccan", "pala", "chalukya", "pandya", "pallava", "rashtrakuta",
                    "kushan", "satavahana", "hoysala", "kakatiya", "ahom",
                    "sikh", "hindustan", "sindh", "punjab", "gujarat", "nepal",
                    "sri lanka", "ceylon", "sinhala", "kashmir", "travancore",
                    "hyderabad", "marwar", "mewar", "awadh", "bahmani", "sur empire"]),
    ("southeast-asia", ["khmer", "cambodia", "angkor", "vietnam", "viet", "đại việt",
                        "dai viet", "champa", "thai", "thailand", "siam", "sukhothai",
                        "ayutthaya", "thonburi", "burma", "myanmar", "pagan", "toungoo",
                        "konbaung", "java", "javanese", "majapahit", "srivijaya",
                        "singhasari", "malacca", "malay", "sumatra", "laos", "lan xang",
                        "philippines", "mataram", "brunei", "aceh", "bali",
                        "polonnaruwa", "anuradhapura"]),
    ("east-asia", ["china", "chinese", "han dynasty", "tang", "song dynasty", "ming",
                   "qing", "yuan dynasty", "sui", "jin dynasty", "zhou", "qin",
                   "shang", "xia", "liao", "western xia", "japan", "japanese",
                   "korea", "korean", "joseon", "goryeo", "silla", "goguryeo",
                   "baekje", "balhae", "manchu", "tibet", "tibetan", "ryukyu",
                   "shu han", "cao wei", "eastern wu", "northern wei", "southern"]),
    ("africa", ["egypt", "egyptian", "pharaoh", "nubia", "kush", "kushite", "aksum",
                "axum", "ethiopia", "ethiopian", "abyssinia", "mali empire", "songhai",
                "ghana empire", "kanem", "bornu", "morocco", "moroccan", "almohad",
                "almoravid", "saadi", "alawi", "marinid", "idrisid", "tunisia",
                "ifriqiya", "carthage", "numidia", "mauretania", "kongo", "ndongo",
                "matamba", "zimbabwe", "mutapa", "ashanti", "dahomey", "benin",
                "oyo", "hausa", "zazzau", "kano", "mamluk", "fatimid egypt",
                "libya", "algeria", "sudan", "somalia", "swahili", "kilwa",
                "madagascar", "merina", "buganda", "rwanda", "africa"]),
    ("north-america", ["united states", "u.s.", "mexico", "mexican", "mexica",
                       "aztec", "maya", "mayan", "toltec", "mixtec", "zapotec",
                       "olmec", "tenochtitlan", "texcoco", "tlacopan", "new spain",
                       "palenque", "copán", "copan", "tikal", "calakmul", "yucatan",
                       "yucatán", "purépecha", "purepecha", "tarascan", "guatemala",
                       "honduras", "el salvador", "nicaragua", "costa rica", "panama",
                       "cuba", "cuban", "haiti", "haitian", "dominican", "jamaica",
                       "canada", "canadian", "quiché"]),
    ("south-america", ["brazil", "brazilian", "argentina", "argentine", "colombia",
                       "colombian", "gran colombia", "new granada", "venezuela",
                       "venezuelan", "peru", "peruvian", "chile", "chilean", "bolivia",
                       "bolivian", "ecuador", "ecuadorian", "paraguay", "uruguay",
                       "guyana", "suriname", "inca", "cusco", "cuzco", "andes",
                       "chimor", "chimú", "muisca", "patagonia", "la plata",
                       "río de la plata", "quito", "charcas"]),
]


def _yr(v):
    if not v:
        return None
    neg = v.startswith("-")
    body = v[1:] if neg else v
    try:
        y = int(body.split("-", 1)[0])
    except (ValueError, IndexError):
        return None
    return -y if neg else y


def classify(label):
    if not label:
        return None
    s = label.lower()
    # "holy roman" must route to Germany even though it contains "roman"
    if "holy roman" in s:
        return "germany"
    for region, words in REGION_RULES:
        for w in words:
            if w in s:
                return region
    return None


def _is_excluded(label):
    s = (label or "").lower()
    return any(w in s for w in EXCLUDE_WORDS)


SLICE_QUERY = """
SELECT DISTINCT ?person ?title ?start ?end ?img ?pos ?p17 ?p27 ?sl ?dod WHERE {
  ?pos wdt:P279* wd:Q116 .
  ?person wdt:P31 wd:Q5 ; p:P39 ?st .
  ?st ps:P39 ?pos ; pq:P580 ?start .
  OPTIONAL { ?st pq:P582 ?end }
  ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title .
  OPTIONAL { ?person wdt:P18 ?img }
  OPTIONAL { ?pos wdt:P17 ?p17 }
  OPTIONAL { ?person wdt:P27 ?p27 }
  OPTIONAL { ?person wikibase:sitelinks ?sl }
  OPTIONAL { ?person wdt:P570 ?dod }
  FILTER(YEAR(?start) >= %d && YEAR(?start) < %d)
}
"""

# Heads of government — Italian prime ministers, German (and Austrian)
# chancellors. Queried separately because they are not heads of state.
HOG_COUNTRIES = ["Q38", "Q183", "Q40"]


def _qid(uri):
    return uri.rsplit("/", 1)[-1] if uri else None


# Head-of-state query, parameterised by (country VALUES, position class). Americas
# use Q48352 (head of state — also catches the Brazilian/Mexican emperors); Europe
# uses Q30461 (president) so we don't re-pull every European monarch.
HOS_QUERY = """
SELECT DISTINCT ?person ?title ?start ?end ?img ?pos ?p17 ?p27 ?sl ?dod WHERE {
  VALUES ?p17 { %s }
  ?pos wdt:P17 ?p17 ; wdt:P279* wd:%s .
  ?person wdt:P31 wd:Q5 ; p:P39 ?st .
  ?st ps:P39 ?pos ; pq:P580 ?start .
  OPTIONAL { ?st pq:P582 ?end }
  ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title .
  OPTIONAL { ?person wdt:P18 ?img }
  OPTIONAL { ?person wdt:P27 ?p27 }
  OPTIONAL { ?person wikibase:sitelinks ?sl }
  OPTIONAL { ?person wdt:P570 ?dod }
  FILTER(YEAR(?start) >= 1750)
}
"""


# Heads of government queried by citizenship (P27) — national PM/chancellor
# offices are attached to historical state entities, not the modern country, so
# matching the position's country misses them. The ruling-span filter then keeps
# only the national office (mayors / state premiers are excluded).
HOG_QUERY = """
SELECT DISTINCT ?person ?title ?start ?end ?img ?pos ?p17 ?p27 ?sl ?dod WHERE {
  ?person wdt:P27 wd:%s ; wdt:P31 wd:Q5 ; p:P39 ?st .
  ?st ps:P39 ?pos ; pq:P580 ?start .
  ?pos wdt:P279* wd:Q2285706 .
  FILTER NOT EXISTS { ?pos wdt:P279* wd:Q30185 }
  OPTIONAL { ?st pq:P582 ?end }
  ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title .
  OPTIONAL { ?person wdt:P18 ?img }
  OPTIONAL { ?pos wdt:P17 ?p17 }
  OPTIONAL { ?person wikibase:sitelinks ?sl }
  OPTIONAL { ?person wdt:P570 ?dod }
  FILTER(YEAR(?start) >= 1800)
}
"""


def _merge(people, rows):
    for r in rows:
        pid = _qid(r["person"]["value"])
        p = people.get(pid)
        if not p:
            p = people[pid] = {
                "qid": pid, "title": r["title"]["value"],
                "spans": [], "img": None, "sl": 0, "dod": None,
                "p17": set(), "p27": set(),
            }
        sy = _yr(r.get("start", {}).get("value"))
        ey = _yr(r.get("end", {}).get("value"))
        # one (position, start, end) per row — reign is later computed from the
        # ruling positions only, so a politician's mayoral side-offices don't
        # stretch the span.
        pos_q = _qid(r["pos"]["value"]) if r.get("pos") else None
        if sy is not None:
            p["spans"].append((pos_q, sy, ey))
        if r.get("dod"):
            dy = _yr(r["dod"]["value"])
            if dy is not None:
                p["dod"] = dy if p["dod"] is None else min(p["dod"], dy)
        if r.get("img"):
            p["img"] = r["img"]["value"]
        if r.get("sl"):
            try:
                p["sl"] = max(p["sl"], int(r["sl"]["value"]))
            except ValueError:
                pass
        for k in ("p17", "p27"):
            if r.get(k):
                p[k].add(_qid(r[k]["value"]))


def _safe_rows(query, what):
    """Run a WDQS query, returning [] (not crashing) if it fails after retries —
    WDQS gets overloaded, and one flaky slice shouldn't abort the whole roster."""
    try:
        return wd.query(query)["results"]["bindings"]
    except Exception as e:
        print(f"  !! {what} failed ({e!r}); skipping", flush=True)
        return []


def fetch_candidates():
    """Run the sliced monarch queries + the American/European head-of-state
    (president) queries, aggregating one record per person. Resilient: a failed
    WDQS slice is skipped rather than aborting the run."""
    people = {}
    for (a, b) in SLICES:
        rows = _safe_rows(SLICE_QUERY % (a, b), f"slice [{a}..{b})")
        print(f"  slice [{a}..{b}): {len(rows)} rows", flush=True)
        _merge(people, rows)
        time.sleep(2)
    # American heads of state
    values = " ".join("wd:" + q for q in AMERICAN_COUNTRIES)
    rows = _safe_rows(HOS_QUERY % (values, "Q48352"), "presidents (Americas)")
    print(f"  presidents (Americas): {len(rows)} rows", flush=True)
    _merge(people, rows)
    time.sleep(2)
    # European presidents (republics)
    values = " ".join("wd:" + q for q in EUROPEAN_COUNTRIES)
    rows = _safe_rows(HOS_QUERY % (values, "Q30461"), "presidents (Europe)")
    print(f"  presidents (Europe): {len(rows)} rows", flush=True)
    _merge(people, rows)
    time.sleep(2)
    # NOTE: national PMs / chancellors come from the curated EXTRA_CURATED table
    # in build_seed.py — the WDQS head-of-government queries proved too heavy /
    # flaky (their offices hang off historical-state entities, and broad
    # citizenship scans time out). Curated marquee heads of government cover the
    # ask reliably; re-enable a WDQS pass here if a robust query is found.
    return people


def main():
    print("augment: building curated spine", flush=True)
    curated = bs.curated_records()

    # curated QIDs (resolve wp titles) so we never duplicate a curated ruler
    print("augment: resolving curated QIDs", flush=True)
    resolved = wp.resolve([r["wp"] for r in curated if r.get("wp")])
    curated_qids = {info.get("qid") for info in resolved.values() if info.get("qid")}

    print("augment: querying Wikidata (sliced)", flush=True)
    people = fetch_candidates()
    print(f"augment: {len(people)} distinct candidate rulers", flush=True)

    # resolve labels for every position / country / citizenship qid we saw
    label_qids = set()
    for p in people.values():
        label_qids |= p["p17"] | p["p27"]
        label_qids |= {pos for (pos, _, _) in p["spans"] if pos}
    print(f"augment: resolving {len(label_qids)} labels", flush=True)
    ents = wd.entities(sorted(label_qids))
    label = {q: wd.label(e) for q, e in ents.items() if "missing" not in e}

    # build augmented records
    by_region = defaultdict(list)
    for p in people.values():
        if p["qid"] in curated_qids:
            continue
        # reign from the RULING positions only — so a politician's mayoral /
        # ministerial side-offices don't stretch the span.
        ruling = [(pos, s, e) for (pos, s, e) in p["spans"]
                  if not _is_excluded(label.get(pos, ""))]
        if p["spans"] and not ruling:
            continue  # only clergy / consort / mayoral / titular positions
        use = ruling or p["spans"]
        starts = [s for (_, s, _) in use if s is not None]
        if not starts:
            continue
        ends = [e for (_, _, e) in use if e is not None]
        rf = min(starts)
        latest = max(starts)
        rt = max(ends) if ends else latest
        # ongoing term: no recorded end (or a term began at/after the last recorded
        # end), and recent -> runs to the present.
        if latest >= 1980 and (not ends or latest >= max(ends)):
            rt = PRESENT
        # never reign past death — fixes acting/interim roles with no recorded end
        # being extended to the present (e.g. Spadolini, d. 1994).
        dod = p["dod"]
        if dod is not None and rf <= dod < rt:
            rt = dod
        if rt < rf:
            rf, rt = rt, rf
        if rf < bs.MERIDIAN_FLOOR or rf > MAX_START:
            continue
        if (rt - rf) > MAX_REIGN:
            continue
        ruling_labels = [label.get(pos) for (pos, _, _) in use if label.get(pos)]
        # region: prefer position-country, then citizenship, then a ruling position
        region = None
        for q in list(p["p17"]) + list(p["p27"]):
            region = classify(label.get(q))
            if region:
                break
        if not region:
            for l in ruling_labels:
                region = classify(l)
                if region:
                    break
        if not region:
            continue
        # realm: the ruling position with the longest span, preferring one in-region
        cand = [t for t in use if label.get(t[0])]
        realm = None
        if cand:
            in_region = [t for t in cand if classify(label.get(t[0])) == region]
            best = max(in_region or cand, key=lambda t: (t[2] or rt) - (t[1] or rf))
            realm = label.get(best[0])
        if not realm:
            realm = next((label[q] for q in p["p17"] if label.get(q)), None)
        realm = realm or bs.REGION_LABEL[region]
        by_region[region].append({
            "title": p["title"], "realm": realm, "rf": rf, "rt": rt,
            "img": p["img"], "sl": p["sl"],
        })

    # No cap — display every ruler we can cleanly place. (TARGETS is retained only
    # as documentation of the old per-region balance.) Sort best-known first so the
    # catalogue still reads sensibly and any future cap is easy to re-impose.
    curated_counts = defaultdict(int)
    for r in curated:
        curated_counts[r["region"]] += 1

    augmented = []
    for region, cands in by_region.items():
        cands.sort(key=lambda c: (c["sl"], 1 if c["img"] else 0, c["rt"] - c["rf"]), reverse=True)
        for c in cands:
            augmented.append(bs.make_record(
                c["title"], c["title"], c["realm"], c["rf"], c["rt"], None,
                region, source="wikidata"))
        print(f"  {region:16} curated {curated_counts[region]:3} + augmented "
              f"{len(cands):4}")

    out = bs.finalize(curated + augmented)
    bs.write_seed(out)
    bs.report(out)


if __name__ == "__main__":
    main()
