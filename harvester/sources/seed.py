"""The spine: load the vendored world roster (seed.json).

This is not an enricher — it is the canonical list every enricher decorates.
The orchestrator calls `load()` first; the result is the curated set of world
rulers (by region and era), in chronological catalogue order. See
../build_seed.py for the roster itself and how seed.json is produced.
"""

import json
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed.json"


def load():
    raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    rulers = []
    for e in raw:
        r = dict(e)
        r["sources"] = {}
        rulers.append(r)
    return rulers
