"""Server-side persona grounding.

Mirrors `web/chat.js : buildPersonaPrompt()` so the browser preview and the real
backend ground the avatar on exactly the same facts. The prompt is assembled
*only* from the harvested record (Wikidata facts + the Wikipedia lead) — the
model is told to stay faithful to it and to admit the limits of its knowledge.

Reads the per-ruler detail files the harvester writes to `data/rulers/<id>.json`
(DATA_DIR points at the repo's data/ dir, or a mounted copy in Docker).
"""

import json
import os
from pathlib import Path

DATA_DIR = Path(
    os.environ.get("PAST_DATA_DIR")
    or os.environ.get("ROAR_DATA_DIR")
    or (Path(__file__).resolve().parents[2] / "data")
)


def load_ruler(ruler_id):
    path = DATA_DIR / "rulers" / f"{ruler_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_year(y):
    if y is None:
        return None
    return f"{-y} BC" if y < 0 else f"AD {y}"


def _range(a, b):
    fa, fb = _fmt_year(a), _fmt_year(b)
    if fa and fb:
        return fa if fa == fb else f"{fa} – {fb}"
    return fa or fb or "dates uncertain"


def build_persona_prompt(r):
    """Assemble the grounding system prompt for ruler record `r`."""
    who = f", {r['wp_description'].lower()}" if r.get("wp_description") else ""
    lines = [
        f"You are {r['name']}{who}. You speak in the first person, as yourself.",
        "",
        "Hold faithfully to this record; do not invent biography beyond it or beyond "
        "well-established history:",
    ]
    if r.get("birth_year") or r.get("death_year"):
        lines.append(f"- Lived: {_range(r.get('birth_year'), r.get('death_year'))}.")
    if r.get("reign_from") or r.get("reign_to"):
        lines.append(f"- Reigned: {_range(r.get('reign_from'), r.get('reign_to'))}.")
    if r.get("realm"):
        lines.append(f"- Realm: {r['realm']}.")
    if r.get("region_label"):
        lines.append(f"- Part of the world: {r['region_label']}.")
    if r.get("birthplace"):
        lines.append(f"- Born at: {r['birthplace']}.")
    if r.get("predecessor"):
        lines.append(f"- Came after: {r['predecessor']}.")
    if r.get("successor"):
        lines.append(f"- Followed by: {r['successor']}.")
    parents = [p for p in (r.get("father"), r.get("mother")) if p]
    if parents:
        lines.append(f"- Parents: {' and '.join(parents)}.")
    if r.get("children"):
        lines.append(f"- Children: {', '.join(r['children'][:6])}.")
    if r.get("positions"):
        lines.append(f"- Titles held: {', '.join(r['positions'][:8])}.")
    if r.get("extract"):
        lines += ["", "Biography (from Wikipedia — your memory of your own life):", r["extract"]]
    lines += [
        "",
        "Manner: measured, period-appropriate, a little imperious but never modern. "
        "If asked about events after your death or beyond the record, admit the limits of "
        "your knowledge. Never claim knowledge of the modern world. Keep replies to a few "
        "sentences. Defer always to the historical record.",
    ]
    return "\n".join(lines)
