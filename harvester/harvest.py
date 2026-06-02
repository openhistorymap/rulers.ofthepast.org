"""Orchestrator for rulers.ofthepast.org.

Loads the spine (the curated world roster, seed.json), runs each enricher in
`sources.REGISTRY` in isolation (a failing enricher is marked `stale`; the
spine and the other enrichers survive), derives timeline years, then writes:

  - data/rulers.json        compact index for the synchronic gallery + meridian
  - data/rulers/<id>.json   full per-ruler detail (bio, relations, links)
  - data/manifest.json      generated_at, totals, region + era tables, bounds,
                            and the handoff back to rulers.ofancientrome.org

Where the sibling site rulers.ofancientrome.org is one line of succession, this
one is a *synchronic atlas*: the hero is the year, and the question is who held
power across the world at the same time. So placement turns on the reign span
(curated in the seed, only filled from Wikidata where blank), and the data is
grouped by region (the lanes) and era (the coloured ages), not by dynasty.

The story runs the other way at the boundary: where Rome falls in 476, *that*
site hands off to this one — so here the manifest records the handoff *back*,
rendered as the "before this, the rulers of Ancient Rome" card.

Environment:
  OTP_DISABLE=wikipedia       skip these enrichers (comma-separated)
  ROAR_DISABLE=...            also honoured (sibling alias)
"""

import datetime
import json
import os
import sys
import time
import traceback
from pathlib import Path

from . import sources
from .build_seed import ERAS, MERIDIAN_FLOOR, REGIONS
from .sources import seed

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RULER_DIR = DATA_DIR / "rulers"

# The reverse handoff: this site begins where Rome ends. The card points back
# to the sibling for the full Roman line of kings, consuls, and emperors.
HANDOFF = {
    "year": 476,
    "site": "rulers.ofancientrome.org",
    "url": "https://rulers.ofancientrome.org",
    "label": "the Rulers of Ancient Rome",
    "note": "The thrones of the world reach back past the edge of this atlas. "
            "For the unbroken line of Rome — every king, consul, and emperor "
            "down to the fall of the West in 476 — cross to the sibling gallery.",
}

# Fields promoted into the compact index (data/rulers.json). Everything else
# stays in the per-ruler detail file.
INDEX_FIELDS = [
    "id", "order", "name", "region", "region_label", "realm", "era", "era_label",
    "wp_description", "blurb", "thumbnail",
    "display_from", "display_to", "reign_from", "reign_to",
    "birth_year", "death_year", "chat_ready",
]


def _disabled():
    raw = (os.environ.get("OTP_DISABLE") or os.environ.get("ROAR_DISABLE") or "").strip()
    return {s.strip() for s in raw.split(",") if s.strip()}


def _pick(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


def _derive_timeline(r):
    """Best (display_from, display_to) signed years for placing a ruler on the
    meridian. Reign is the spine of this site, so it leads; lifespan and the
    seed years are fallbacks for the rare figure with no recorded reign span."""
    df = _pick(r.get("reign_from"), r.get("year_from"), r.get("birth_year"))
    dt = _pick(r.get("reign_to"), r.get("year_to"), r.get("death_year"))
    r["display_from"] = df
    r["display_to"] = dt


def _write_json(path, obj, pretty=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        if pretty:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
        else:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rulers = seed.load()
    print(f"rulers.ofthepast.org harvest · spine: {len(rulers)} rulers", flush=True)

    disabled = _disabled()
    enabled = [s for s in sources.REGISTRY if s.name not in disabled]
    ctx = {}
    source_status = {}
    started = datetime.datetime.now(datetime.timezone.utc)

    for src in enabled:
        print(f"\n[{src.name}] {src.title}", flush=True)
        t0 = time.monotonic()
        try:
            status = src.run(rulers, ctx)
        except Exception as e:
            elapsed = time.monotonic() - t0
            print(f"  !! failed after {elapsed:.1f}s: {e!r}", flush=True)
            traceback.print_exc()
            source_status[src.name] = {"status": "stale", "error": repr(e)}
            continue
        elapsed = time.monotonic() - t0
        status = {**status, "elapsed_seconds": round(elapsed, 1)}
        source_status[src.name] = status
        print(f"  -> {status}", flush=True)
        time.sleep(1)

    for src in sources.REGISTRY:
        if src.name not in source_status:
            source_status[src.name] = {"status": "disabled"}

    # derive timeline years
    for r in rulers:
        _derive_timeline(r)

    # write per-ruler detail files + compact index. Clear stale detail files
    # first so a renamed/removed ruler id never leaves an orphan behind.
    RULER_DIR.mkdir(parents=True, exist_ok=True)
    current_ids = {r["id"] for r in rulers}
    for f in RULER_DIR.glob("*.json"):
        if f.stem not in current_ids:
            f.unlink()
    index = []
    for r in rulers:
        _write_json(RULER_DIR / f"{r['id']}.json", r)
        index.append({k: r.get(k) for k in INDEX_FIELDS})
    _write_json(DATA_DIR / "rulers.json", index)

    # bounds for the meridian scale. The lower bound is floored to MERIDIAN_FLOOR
    # (9000 BC) so the timeline reaches back into deep prehistory — the long
    # "Before the Kings" stretch, empty because kingship is younger than writing.
    years = [y for r in rulers for y in (r.get("display_from"), r.get("display_to")) if y is not None]
    bounds = {"min_year": min(min(years), MERIDIAN_FLOOR), "max_year": max(years)} if years else {}

    # region + era tables (ordered, with counts) — the frontend reads lane order
    # and era boundaries from here, so they live in one place (build_seed).
    region_counts = {}
    era_counts = {}
    for r in rulers:
        region_counts[r.get("region")] = region_counts.get(r.get("region"), 0) + 1
        era_counts[r.get("era")] = era_counts.get(r.get("era"), 0) + 1
    regions = [{"key": k, "label": l, "count": region_counts.get(k, 0)} for k, l in REGIONS]
    era_rows = []
    prev = None
    for key, label, upper in ERAS:
        era_rows.append({
            "key": key,
            "label": label,
            "from": prev,
            "to": (None if upper >= 9999 else upper),
            "count": era_counts.get(key, 0),
        })
        prev = upper
    eras = era_rows

    finished = datetime.datetime.now(datetime.timezone.utc)
    manifest = {
        "generated_at": finished.isoformat(timespec="seconds"),
        "title": "Rulers of the Past",
        "tagline": "Who ruled the world at the same time — antiquity to the eighteenth century",
        "totals": {
            "rulers": len(rulers),
            "with_image": sum(1 for r in rulers if r.get("thumbnail") or r.get("image")),
            "with_extract": sum(1 for r in rulers if r.get("extract")),
            "chat_ready": sum(1 for r in rulers if r.get("chat_ready")),
            "regions": len(regions),
        },
        "regions": regions,
        "eras": eras,
        "bounds": bounds,
        "handoff": HANDOFF,
        "sources": source_status,
    }
    _write_json(DATA_DIR / "manifest.json", manifest, pretty=True)

    elapsed = (finished - started).total_seconds()
    print(f"\ndone in {elapsed:.0f}s. totals: {manifest['totals']}", flush=True)
    stale = [n for n, s in source_status.items() if s.get("status") == "stale"]
    if stale:
        print(f"  stale sources: {stale}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
