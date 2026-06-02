"""Enricher registry.

To add an enrichment source:
  1. Create `harvester/sources/<name>_enrich.py` exposing a module-level
     `SOURCE` of type `base.Enricher`.
  2. Import it here and append to `REGISTRY` (declaration order = run order).
  3. Disable per-run with the ROAR_DISABLE env var (comma-separated names).

The spine (`seed.py`) is loaded by the orchestrator before any enricher runs;
it is not in this registry.
"""

from . import wikidata_enrich, wikipedia_enrich

REGISTRY = [
    wikidata_enrich.SOURCE,
    wikipedia_enrich.SOURCE,
]


def by_name(name):
    for s in REGISTRY:
        if s.name == name:
            return s
    return None
