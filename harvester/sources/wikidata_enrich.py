"""Wikidata enricher.

For every ruler on the spine:
  1. resolve its curated en.wikipedia title to a Wikidata QID (via the page's
     `wikibase_item` pageprop);
  2. pull the entity and fill structured facts — birth/death years, reign
     (start/end qualifiers on the 'Roman emperor' / 'King of Rome' position),
     lead image, dynastic family, predecessor/successor, parents/children,
     birthplace (+coordinates) and deathplace;
  3. resolve all the referenced QIDs (families, places, relatives, positions)
     to English labels in one extra batched pass, and cross-link
     predecessor/successor to our own roster ids where they coincide.

Everything is best-effort: a ruler with no Wikidata match keeps its seed fields
and is simply not decorated. A hard failure of the whole stage is caught by the
orchestrator and recorded as `stale`.
"""

from .. import wikidata as wd
from .. import wikipedia as wp
from .base import Enricher


def _coords(entity):
    for st in wd.claims(entity, wd.P_COORDS):
        v = (st.get("mainsnak") or {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "latitude" in v and "longitude" in v:
            return [round(v["longitude"], 5), round(v["latitude"], 5)]
    return None


def run(rulers, ctx):
    # 1. title -> qid
    titles = [r["wp"] for r in rulers if r.get("wp")]
    resolved = wp.resolve(titles)
    for r in rulers:
        info = resolved.get(r.get("wp"), {})
        r["qid"] = info.get("qid")
        r["wikidata_url"] = f"https://www.wikidata.org/wiki/{r['qid']}" if r.get("qid") else None

    qids = [r["qid"] for r in rulers if r.get("qid")]
    ents = wd.entities(qids)
    qid_to_id = {r["qid"]: r["id"] for r in rulers if r.get("qid")}

    # 2. fill fields + collect referenced qids
    refs = set()
    matched = 0
    non_human = []
    rel_props = [wd.P_FAMILY, wd.P_REPLACES, wd.P_REPLACED_BY, wd.P_FATHER,
                 wd.P_MOTHER, wd.P_CHILD, wd.P_BIRTHPLACE, wd.P_DEATHPLACE]
    for r in rulers:
        e = ents.get(r.get("qid"))
        if not e or "missing" in e:
            r["sources"]["wikidata"] = "no-match"
            continue
        if not wd.is_human(e):
            # Gracchi (a pair) and a couple of group articles are legitimately
            # non-human; keep them but flag for the manifest.
            non_human.append(r["id"])
        matched += 1
        r["wd_label"] = wd.label(e)
        r["wd_description"] = wd.description(e)
        r["birth_year"] = wd.year_of(e, wd.P_BIRTH)
        r["death_year"] = wd.year_of(e, wd.P_DEATH)
        # The curated seed reign is authoritative for placement; only fill from
        # Wikidata where the seed left a gap.
        rf, rt = wd.reign_years(e)
        r["reign_from"] = r.get("reign_from") if r.get("reign_from") is not None else rf
        r["reign_to"] = r.get("reign_to") if r.get("reign_to") is not None else rt
        r["reign_wikidata"] = [rf, rt]
        r["image"] = wd.image_url(e)
        r["family_qid"] = wd.first_qid(e, wd.P_FAMILY)
        # Succession: entity-level P1365/P1366 first, else the ruling-position
        # qualifiers (where Roman succession actually lives).
        pre_q = wd.first_qid(e, wd.P_REPLACES)
        suc_q = wd.first_qid(e, wd.P_REPLACED_BY)
        if not pre_q or not suc_q:
            rp, rs = wd.reign_succession(e)
            pre_q, suc_q = pre_q or rp, suc_q or rs
        r["predecessor_qid"] = pre_q
        r["successor_qid"] = suc_q
        r["father_qid"] = wd.first_qid(e, wd.P_FATHER)
        r["mother_qid"] = wd.first_qid(e, wd.P_MOTHER)
        r["children_qids"] = wd.all_qids(e, wd.P_CHILD)
        r["birthplace_qid"] = wd.first_qid(e, wd.P_BIRTHPLACE)
        r["deathplace_qid"] = wd.first_qid(e, wd.P_DEATHPLACE)
        r["position_qids"] = wd.positions_held(e)
        for p in rel_props:
            refs.update(wd.all_qids(e, p))
        refs.update(r["position_qids"])
        refs.update(q for q in (r["predecessor_qid"], r["successor_qid"]) if q)
        r["sources"]["wikidata"] = "ok"

    # 3. resolve referenced qids -> labels (+ coords for places)
    refents = wd.entities(sorted(q for q in refs if q))
    labels = {q: wd.label(e) for q, e in refents.items() if "missing" not in e}
    place_coords = {q: _coords(e) for q, e in refents.items() if "missing" not in e}

    def lbl(q):
        return labels.get(q) if q else None

    for r in rulers:
        if r["sources"].get("wikidata") not in ("ok",):
            continue
        r["family"] = lbl(r.get("family_qid"))
        r["predecessor"] = lbl(r.get("predecessor_qid"))
        r["successor"] = lbl(r.get("successor_qid"))
        r["predecessor_id"] = qid_to_id.get(r.get("predecessor_qid"))
        r["successor_id"] = qid_to_id.get(r.get("successor_qid"))
        r["father"] = lbl(r.get("father_qid"))
        r["father_id"] = qid_to_id.get(r.get("father_qid"))
        r["mother"] = lbl(r.get("mother_qid"))
        r["children"] = [lbl(q) for q in (r.get("children_qids") or []) if lbl(q)]
        r["birthplace"] = lbl(r.get("birthplace_qid"))
        r["birthplace_coord"] = place_coords.get(r.get("birthplace_qid"))
        r["deathplace"] = lbl(r.get("deathplace_qid"))
        r["deathplace_coord"] = place_coords.get(r.get("deathplace_qid"))
        r["positions"] = [lbl(q) for q in (r.get("position_qids") or []) if lbl(q)]

    ctx["qid_to_id"] = qid_to_id
    return {
        "status": "ok",
        "matched": matched,
        "total": len(rulers),
        "no_match": [r["id"] for r in rulers if r["sources"].get("wikidata") == "no-match"],
        "non_human": non_human,
        "referenced_labels": len(labels),
    }


SOURCE = Enricher(name="wikidata", title="Wikidata · structured facts", run=run)
