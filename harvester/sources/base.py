"""Enricher-plugin contract.

This site's harvester is shaped a little differently from its map siblings
(map.ofww1.org et al.). There, independent sources each emit a FeatureCollection
that the orchestrator merges. Here there is a single, ordered **spine** — the
infoplease roster loaded from `seed.json` — and each plugin *enriches every
ruler in place* from a different upstream (Wikidata, Wikipedia, …).

So a plugin is an `Enricher`: `run(rulers, ctx)` walks the shared `rulers` list,
fills fields, and returns a status dict. Per-plugin failure is isolated by the
orchestrator: an exception in one enricher is caught and recorded as `stale` in
the manifest; the spine and every other enricher's output survive. Old
enrichers cannot break because of new ones.

`ctx` is a plain dict the orchestrator threads through every enricher, for
sharing cheap derived state (e.g. the resolved QID map) between stages.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Enricher:
    name: str                                   # stable id: "wikidata", "wikipedia"
    title: str                                  # human description (logs/manifest)
    run: Callable[[list, dict], dict]           # (rulers, ctx) -> status dict
