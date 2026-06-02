"""Minimal Wikidata client for rulers.ofancientrome.org.

Two ways in:
  - `entities(qids)`  — batched `wbgetentities` (50 ids/call) returning the full
    entity JSON (claims with qualifiers, sitelinks, labels). This is how the
    harvester pulls structured facts per ruler.
  - `query(sparql)`   — the WDQS SPARQL client cloned from the OHM atlases
    (map.ofww1.org), kept for ad-hoc/catalog queries. Not used by the default
    pipeline but handy and intentionally kept in sync with its siblings.

Claim helpers (`first_qid`, `times`, `qualifier_years`, …) keep the source
modules free of Wikidata's nested snak structure.
"""

import time
import urllib.parse

import requests

WB_API = "https://www.wikidata.org/w/api.php"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
UA = "rulers.ofancientrome.org/1.0 (https://github.com/openhistorymap/rulers.ofancientrome.org; OpenHistoryMap)"

COMMONS_FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/"


# --- Property ids we care about ---------------------------------------------
P_INSTANCE_OF = "P31"
P_IMAGE = "P18"
P_BIRTH = "P569"
P_DEATH = "P570"
P_POSITION_HELD = "P39"
P_START = "P580"
P_END = "P582"
P_FATHER = "P22"
P_MOTHER = "P25"
P_CHILD = "P40"
P_SPOUSE = "P26"
P_FAMILY = "P53"          # noble/dynastic family
P_REPLACES = "P1365"      # predecessor
P_REPLACED_BY = "P1366"   # successor
P_BIRTHPLACE = "P19"
P_DEATHPLACE = "P20"
P_COORDS = "P625"

Q_HUMAN = "Q5"
# A few well-known ruling positions, used only to *prefer* one P39 statement's
# start/end as the reign when a figure held several dated positions. For a world
# roster we cannot enumerate every throne, so `reign_years` falls back to the
# widest start/end across all positions held (see below).
RULING_POSITIONS = {
    "Q842606",   # Roman emperor
    "Q207338",   # King of Rome
    "Q12097",    # king
    "Q116",      # monarch
    "Q12101713", # emperor
}


class WdqsTimeout(Exception):
    pass


def _get(url, params, attempts=4, http_timeout=120):
    last = None
    for i in range(attempts):
        try:
            r = requests.get(
                url,
                params=params,
                headers={"User-Agent": UA, "Accept": "application/json"},
                timeout=http_timeout,
            )
            if r.status_code in (429, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                time.sleep(10 + 10 * i)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = repr(e)
            time.sleep(5 + 5 * i)
    raise RuntimeError(f"wikidata request failed: {last}")


# --- wbgetentities ----------------------------------------------------------
def entities(qids, chunk=50):
    """Return {qid: entity_dict} for the given QIDs, batched."""
    out = {}
    ids = [q for q in dict.fromkeys(qids) if q]
    for i in range(0, len(ids), chunk):
        batch = ids[i : i + chunk]
        data = _get(
            WB_API,
            {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "claims|labels|descriptions|sitelinks",
                "languages": "en",
                "sitefilter": "enwiki",
                "format": "json",
            },
        )
        out.update(data.get("entities", {}))
        time.sleep(1)
    return out


# --- claim accessors --------------------------------------------------------
def claims(entity, pid):
    return (entity.get("claims") or {}).get(pid, []) or []


def _mainsnak(stmt):
    return (stmt.get("mainsnak") or {}) if stmt else {}


def _dv(snak):
    return (snak.get("datavalue") or {}).get("value")


def first_qid(entity, pid):
    for st in claims(entity, pid):
        v = _dv(_mainsnak(st))
        if isinstance(v, dict) and v.get("id"):
            return v["id"]
    return None


def all_qids(entity, pid):
    out = []
    for st in claims(entity, pid):
        v = _dv(_mainsnak(st))
        if isinstance(v, dict) and v.get("id"):
            out.append(v["id"])
    return out


def first_string(entity, pid):
    for st in claims(entity, pid):
        v = _dv(_mainsnak(st))
        if isinstance(v, str):
            return v
    return None


def label(entity):
    return ((entity.get("labels") or {}).get("en") or {}).get("value")


def description(entity):
    return ((entity.get("descriptions") or {}).get("en") or {}).get("value")


def enwiki_title(entity):
    return ((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title")


def parse_time_year(timeval):
    """Wikidata time value -> signed int year (negative = BC), or None.
    timeval looks like {'time': '+0014-00-00T00:00:00Z', 'precision': 9}."""
    if not timeval:
        return None
    t = timeval.get("time") if isinstance(timeval, dict) else timeval
    if not t:
        return None
    sign = -1 if t.startswith("-") else 1
    body = t[1:] if t[0] in "+-" else t
    try:
        year = int(body.split("-", 1)[0])
    except (ValueError, IndexError):
        return None
    return sign * year


def year_of(entity, pid):
    """Year (signed int) of the first time-valued claim for pid."""
    for st in claims(entity, pid):
        v = _dv(_mainsnak(st))
        if isinstance(v, dict) and v.get("time"):
            y = parse_time_year(v)
            if y is not None:
                return y
    return None


def _qual_year(stmt, pid):
    quals = (stmt.get("qualifiers") or {}).get(pid, [])
    for q in quals:
        v = (q.get("datavalue") or {}).get("value")
        if isinstance(v, dict) and v.get("time"):
            y = parse_time_year(v)
            if y is not None:
                return y
    return None


def reign_years(entity):
    """Best (from, to) signed years for a reign, read from the start/end
    qualifiers (P580/P582) on the figure's positions held (P39).

    Preference: if any held position is a recognised ruling position
    (RULING_POSITIONS), use the start/end of *those* statements; otherwise fall
    back to the widest start/end across every dated P39 statement. This is only
    a fallback for the placement timeline — the curated seed reign wins where it
    is set — so a stray office date can never misplace a known monarch."""
    ruling = ([], [])
    anypos = ([], [])
    for st in claims(entity, P_POSITION_HELD):
        pos = _dv(_mainsnak(st))
        if not isinstance(pos, dict):
            continue
        s = _qual_year(st, P_START)
        e = _qual_year(st, P_END)
        bucket = ruling if pos.get("id") in RULING_POSITIONS else anypos
        if s is not None:
            bucket[0].append(s)
        if e is not None:
            bucket[1].append(e)
        # widest-of-all always also accumulates, so it is a true superset
        if bucket is ruling:
            if s is not None:
                anypos[0].append(s)
            if e is not None:
                anypos[1].append(e)
    starts, ends = (ruling if (ruling[0] or ruling[1]) else anypos)
    return (min(starts) if starts else None, max(ends) if ends else None)


def _qual_qid(stmt, pid):
    for q in (stmt.get("qualifiers") or {}).get(pid, []):
        v = (q.get("datavalue") or {}).get("value")
        if isinstance(v, dict) and v.get("id"):
            return v["id"]
    return None


def reign_succession(entity):
    """(predecessor_qid, successor_qid) read from the ruling-position
    qualifiers (P1365/P1366 on the 'Roman emperor' / 'King of Rome' statement).
    Roman succession is modelled there, not at the entity level."""
    for st in claims(entity, P_POSITION_HELD):
        pos = _dv(_mainsnak(st))
        if isinstance(pos, dict) and pos.get("id") in RULING_POSITIONS:
            pre = _qual_qid(st, P_REPLACES)
            suc = _qual_qid(st, P_REPLACED_BY)
            if pre or suc:
                return pre, suc
    return None, None


def positions_held(entity):
    """Distinct position QIDs held, in first-seen order (Tiberius held the
    consulship five times — we want one 'Roman consul', not five)."""
    return list(dict.fromkeys(all_qids(entity, P_POSITION_HELD)))


def image_url(entity, width=640):
    fn = first_string(entity, P_IMAGE)
    if not fn:
        return None
    return COMMONS_FILEPATH + urllib.parse.quote(fn.replace(" ", "_")) + f"?width={width}"


def is_human(entity):
    return Q_HUMAN in all_qids(entity, P_INSTANCE_OF)


# --- SPARQL (cloned from map.ofww1.org, kept in sync) -----------------------
_TIMEOUT_BODY_MARKERS = (
    "TimeoutException",
    "QueryTimeoutException",
    "java.util.concurrent.ExecutionException",
)


def query(sparql, attempts=3, http_timeout=180):
    last = None
    for i in range(attempts):
        try:
            r = requests.get(
                SPARQL_ENDPOINT,
                params={"query": sparql, "format": "json"},
                headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
                timeout=http_timeout,
            )
            if r.status_code in (429, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                time.sleep(30 + 20 * i)
                continue
            if r.status_code == 500 and any(m in (r.text or "") for m in _TIMEOUT_BODY_MARKERS):
                raise WdqsTimeout("WDQS server-side timeout")
            r.raise_for_status()
            return r.json()
        except WdqsTimeout:
            raise
        except requests.RequestException as e:
            last = repr(e)
            time.sleep(15 + 15 * i)
    raise RuntimeError(f"WDQS failed: {last}")
