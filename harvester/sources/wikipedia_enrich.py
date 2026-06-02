"""Wikipedia enricher.

Pulls the lead-section plain-text extract (the biography blurb shown in the
detail panel and used to ground the future avatar), a short one-line
description, the lead image, and the canonical article URL for every ruler —
all in batched MediaWiki API calls keyed on the same curated title used for
Wikidata resolution.

The extract doubles as the chat-readiness signal: a ruler with a substantial
lead section can host a grounded persona; a one-line stub cannot.
"""

from .. import wikipedia as wp
from .base import Enricher

CHAT_MIN_EXTRACT = 600   # chars of lead extract needed to ground an avatar


def run(rulers, ctx):
    titles = [r["wp"] for r in rulers if r.get("wp")]
    data = wp.extracts(titles)
    filled = 0
    for r in rulers:
        d = data.get(r.get("wp"))
        if not d or not (d.get("extract") or d.get("url")):
            r["sources"]["wikipedia"] = "no-match"
            continue
        r["extract"] = (d.get("extract") or "").strip() or None
        r["wp_description"] = d.get("description")
        r["wikipedia_url"] = d.get("url")
        # Prefer Wikipedia's lead image only if Wikidata gave us none.
        r["image_lead"] = d.get("original") or d.get("thumbnail")
        if not r.get("image"):
            r["image"] = r["image_lead"]
        r["thumbnail"] = d.get("thumbnail") or r.get("image")
        r["chat_ready"] = bool(r["extract"] and len(r["extract"]) >= CHAT_MIN_EXTRACT)
        if r["extract"]:
            filled += 1
        r["sources"]["wikipedia"] = "ok"
    return {
        "status": "ok",
        "extracts": filled,
        "total": len(rulers),
        "chat_ready": sum(1 for r in rulers if r.get("chat_ready")),
        "no_match": [r["id"] for r in rulers if r["sources"].get("wikipedia") == "no-match"],
    }


SOURCE = Enricher(name="wikipedia", title="Wikipedia · biography + lead image", run=run)
