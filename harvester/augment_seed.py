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
    "rome-byzantium": 55,
    "europe-west": 120,
    "europe-east": 70,
    "middle-east": 85,
    "steppe": 28,
    "south-asia": 62,
    "southeast-asia": 38,
    "east-asia": 92,
    "africa": 58,
    "americas": 26,
}

# Century-ish slices over the named-ruler range. Kept small where history is
# dense (medieval / early-modern Europe) so each WDQS query stays well under the
# timeout.
SLICES = [
    (-3300, -500), (-500, 1), (1, 400), (400, 700), (700, 1000),
    (1000, 1200), (1200, 1350), (1350, 1500),
    (1500, 1600), (1600, 1700), (1700, 1801),
]

MAX_REIGN = 80          # drop mythically long "reigns" (data errors / legends)

# Position / title words that are not the sovereigns this atlas is about.
EXCLUDE_WORDS = (
    "bishop", "archbishop", "patriarch", "pope", "cardinal", "abbot", "abbess",
    "consort", "titular", "pretender", "antipope", "claimant", "co-prince",
    "viceroy", "governor", "president", "prime minister", "chancellor",
    "nagid", "exilarch", "rabbi", "high priest", "prophet", "saint",
    "deity", "god ", "goddess", "mytholog",
)

# Region keyword rules — ordered; first substring found in a label wins. Tuned so
# "Holy Roman" beats "Roman", and historical state names route correctly.
REGION_RULES = [
    # rome-byzantium (the Greco-Roman Mediterranean)
    ("rome-byzantium", ["holy roman"]),   # sentinel: handled below as europe-west
    ("rome-byzantium", ["byzan", "eastern roman", "western roman", "roman empire",
                        "roman emperor", "roman republic", "latin empire", "nicaea",
                        "trebizond", "thessalonica", "macedon", "epirus", "achaea",
                        "syracuse", "magna graecia", "hellenistic greece"]),
    ("europe-west", ["holy roman", "france", "french", "england", "english", "britain",
                     "scotland", "scottish", "wales", "welsh", "ireland", "irish",
                     "spain", "spanish", "castile", "aragon", "leon", "navarre",
                     "asturias", "galicia", "portugal", "portuguese", "germany",
                     "german", "prussia", "bavaria", "saxony", "swabia", "franconia",
                     "brandenburg", "palatinate", "württemberg", "hanover", "austria",
                     "habsburg", "italy", "italian", "sicily", "naples", "sardinia",
                     "savoy", "milan", "florence", "tuscany", "venice", "genoa",
                     "papal", "vatican", "lombard", "ostrogoth", "visigoth",
                     "frankish", "franks", "burgundy", "lorraine", "brittany",
                     "normandy", "aquitaine", "netherlands", "holland", "flanders",
                     "brabant", "luxembourg", "belgium", "denmark", "danish",
                     "norway", "norwegian", "sweden", "swedish", "iceland",
                     "switzerland", "swiss", "frisia", "andorra", "monaco", "malta"]),
    ("europe-east", ["russia", "russian", "muscovy", "muscovite", "kievan", "kyiv",
                     "kiev", "rus'", "rus ", " rus", "novgorod", "vladimir-suzdal",
                     "poland", "polish", "lithuania", "lithuanian", "hungary",
                     "hungarian", "bohemia", "bohemian", "czech", "moravia",
                     "serbia", "serbian", "bulgaria", "bulgarian", "croatia",
                     "croatian", "romania", "wallachia", "moldavia", "transylvania",
                     "ukraine", "ukrainian", "belarus", "georgia", "georgian",
                     "armenia", "armenian", "montenegro", "bosnia", "albania",
                     "kievan rus", "galicia-volhynia", "ruthenia", "pomerania",
                     "silesia", "slovakia", "slovenia"]),
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
    ("americas", ["aztec", "maya", "mayan", "inca", "mexico", "mexica", "tenochtitlan",
                  "texcoco", "tlacopan", "mixtec", "zapotec", "toltec", "olmec",
                  "peru", "cusco", "cuzco", "andes", "palenque", "copán", "copan",
                  "tikal", "calakmul", "purépecha", "purepecha", "tarascan",
                  "muisca", "chimor", "chimú", "quiché", "yucatan", "yucatán",
                  "guatemala", "honduras"]),
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
    # "holy roman" must route to europe-west even though it contains "roman"
    if "holy roman" in s:
        return "europe-west"
    for region, words in REGION_RULES:
        if region == "rome-byzantium" and words == ["holy roman"]:
            continue
        for w in words:
            if w in s:
                return region
    return None


def _is_excluded(label):
    s = (label or "").lower()
    return any(w in s for w in EXCLUDE_WORDS)


SLICE_QUERY = """
SELECT DISTINCT ?person ?title ?start ?end ?img ?pos ?p17 ?p27 ?sl WHERE {
  ?pos wdt:P279* wd:Q116 .
  ?person wdt:P31 wd:Q5 ; p:P39 ?st .
  ?st ps:P39 ?pos ; pq:P580 ?start .
  OPTIONAL { ?st pq:P582 ?end }
  ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title .
  OPTIONAL { ?person wdt:P18 ?img }
  OPTIONAL { ?pos wdt:P17 ?p17 }
  OPTIONAL { ?person wdt:P27 ?p27 }
  OPTIONAL { ?person wikibase:sitelinks ?sl }
  FILTER(YEAR(?start) >= %d && YEAR(?start) < %d)
}
"""


def _qid(uri):
    return uri.rsplit("/", 1)[-1] if uri else None


def fetch_candidates():
    """Run the sliced WDQS queries and aggregate one record per person."""
    people = {}
    for (a, b) in SLICES:
        res = wd.query(SLICE_QUERY % (a, b))
        rows = res["results"]["bindings"]
        print(f"  slice [{a}..{b}): {len(rows)} rows", flush=True)
        for r in rows:
            pid = _qid(r["person"]["value"])
            p = people.get(pid)
            if not p:
                p = people[pid] = {
                    "qid": pid, "title": r["title"]["value"],
                    "starts": [], "ends": [], "img": None, "sl": 0,
                    "pos": set(), "p17": set(), "p27": set(),
                }
            sy = _yr(r.get("start", {}).get("value"))
            ey = _yr(r.get("end", {}).get("value"))
            if sy is not None:
                p["starts"].append(sy)
            if ey is not None:
                p["ends"].append(ey)
            if r.get("img"):
                p["img"] = r["img"]["value"]
            if r.get("sl"):
                try:
                    p["sl"] = max(p["sl"], int(r["sl"]["value"]))
                except ValueError:
                    pass
            for k, col in (("pos", "pos"), ("p17", "p17"), ("p27", "p27")):
                if r.get(col):
                    p[k].add(_qid(r[col]["value"]))
        time.sleep(2)
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
        label_qids |= p["pos"] | p["p17"] | p["p27"]
    print(f"augment: resolving {len(label_qids)} labels", flush=True)
    ents = wd.entities(sorted(label_qids))
    label = {q: wd.label(e) for q, e in ents.items() if "missing" not in e}

    # build augmented records
    by_region = defaultdict(list)
    for p in people.values():
        if p["qid"] in curated_qids:
            continue
        if not p["starts"]:
            continue
        rf = min(p["starts"])
        rt = max(p["ends"]) if p["ends"] else max(p["starts"])
        if rt < rf:
            rf, rt = rt, rf
        if rf < bs.MERIDIAN_FLOOR or rf > 1800:
            continue
        if (rt - rf) > MAX_REIGN:
            continue
        pos_labels = [label.get(q) for q in p["pos"] if label.get(q)]
        ruling_pos = [l for l in pos_labels if not _is_excluded(l)]
        if pos_labels and not ruling_pos:
            continue  # purely clergy / consort / titular
        # region: prefer position-country, then citizenship, then position label
        region = None
        for q in p["p17"]:
            region = classify(label.get(q))
            if region:
                break
        if not region:
            for q in p["p27"]:
                region = classify(label.get(q))
                if region:
                    break
        if not region:
            for l in ruling_pos:
                region = classify(l)
                if region:
                    break
        if not region:
            continue
        # realm: a ruling position label that suits the region, else any, else country
        realm = None
        for l in ruling_pos:
            if classify(l) == region:
                realm = l
                break
        realm = realm or (ruling_pos[0] if ruling_pos else None)
        if not realm:
            for q in p["p17"]:
                if label.get(q):
                    realm = label[q]
                    break
        realm = realm or bs.REGION_LABEL[region]
        by_region[region].append({
            "title": p["title"], "realm": realm, "rf": rf, "rt": rt,
            "img": p["img"], "sl": p["sl"],
        })

    # rank within region (best-known first) and cap to the per-region target
    curated_counts = defaultdict(int)
    for r in curated:
        curated_counts[r["region"]] += 1

    augmented = []
    for region, cands in by_region.items():
        cands.sort(key=lambda c: (c["sl"], 1 if c["img"] else 0, c["rt"] - c["rf"]), reverse=True)
        room = max(0, TARGETS.get(region, 40) - curated_counts[region])
        for c in cands[:room]:
            augmented.append(bs.make_record(
                c["title"], c["title"], c["realm"], c["rf"], c["rt"], None,
                region, source="wikidata"))
        print(f"  {region:16} curated {curated_counts[region]:3} + augmented "
              f"{min(room, len(cands)):3} (of {len(cands)} found)")

    out = bs.finalize(curated + augmented)
    bs.write_seed(out)
    bs.report(out)


if __name__ == "__main__":
    main()
