# rulers.ofthepast.org

A **synchronic atlas of world rulers** — who held power, *at the same time*,
across the world, from antiquity to the eighteenth century. Move the **meridian**
to any year and the world's thrones light up together, laid out in region lanes;
for those whose lives are recorded fully enough, you can **speak with an avatar**.

Sibling — in machinery and in story — to **`rulers.ofancientrome.org`** (ROAR).
Same shape: *harvester → static-data → GitHub-Pages*, same avatar shell. Where
ROAR is **one line of succession** (Rome, kings to emperors, cut in travertine),
this is **the whole world on a spine of time** (drawn and inked on vellum). Rome
hands its story off to this site at the fall of the West in 476; here the handoff
runs the other way — the manifest records a handoff **back** to ROAR, rendered as
the "before this atlas — Rome" card.

## Scope (decided up front)

- **The roster is a hybrid of ~870 rulers.** A hand-curated core of ~265 of the
  most recognisable rulers (`harvester/build_seed.py`), topped up per region from
  Wikidata (`harvester/augment_seed.py`) to a balanced ~870. **Thirteen regions**
  (the lanes — Italy and Germany are their own lanes; the Americas split into
  North and South), **seven eras** spanning the deliberately-empty **"Before the
  Kings"** deep-time band (the meridian reaches to 9000 BC, but named rulers begin
  with Narmer ~3100 BC) through to a **Modern** era reaching the present
  (~2026) — monarchs *and* presidents (Wikidata head-of-state queries: Q48352
  over American republics, Q30461 over European republics). Sitting leaders /
  reigning monarchs run to the present, not just their first year.
- **Reign spans, curated in the seed, are authoritative for placement.** The
  whole site turns on "who reigned in year Y", so a stray Wikidata office-date
  must never misplace a known king. The harvester fills reign only where the
  seed left it blank; everything else (portraits, biographies, birth/death,
  succession, places, titles) comes from Wikidata + Wikipedia.
- **Avatar chat is served by the shared API.** `web/chat.js` POSTs to
  `chat.people.ofthepast.org` (repo `openfantasymap/avatars`), the one chat
  service behind all the ruler galleries — it fetches this atlas's published
  per-ruler JSON, grounds the persona, and answers via an OpenAI-compatible
  model. If that backend is unreachable the avatar stays in character with a
  holding reply. It must never fabricate history.
  It must never fabricate history.

## Layout

```
harvester/        Python pipeline (no map deps). `python -m harvester`.
  build_seed.py   THE CURATED CORE. A hand region->[rulers] table; exposes
                  curated_records()/finalize()/write_seed(). `python -m
                  harvester.build_seed` writes just the curated ~255.
  augment_seed.py THE FULL ROSTER (default). Builds the curated core, then tops
                  each region up from Wikidata (sliced WDQS over monarch-class
                  P39 holders) to a per-region TARGET -> ~634. `python -m
                  harvester.augment_seed` (needs network). This is the seed
                  writer for the live site.
  data/seed.json  the canonical spine the harvester reads (committed)
  wikidata.py     wbgetentities + SPARQL client (+ claim helpers). reign_years()
                  is generalised: widest start/end across positions held.
  wikipedia.py    MediaWiki API: title->QID resolve, lead extracts + images
  sources/
    base.py       the Enricher contract
    seed.py       loads the spine (not an enricher)
    wikidata_enrich.py   dates, reign (seed-first), image, family, succession, places
    wikipedia_enrich.py  lead biography + image + chat-readiness
  harvest.py      orchestrator -> data/ (region + era tables, reverse handoff)
web/              static frontend (no build step, relative paths only)
  index.html  style.css  app.js  chat.js  (chat.js calls the shared avatars API)
data/             GENERATED, machine-owned. Committed; published by Deploy.
  rulers.json            compact index for the gallery + meridian
  rulers/<id>.json       full per-ruler detail (bio, relations, links)
  manifest.json          totals, region table, era table, bounds, handoff, sources
.github/workflows/  harvest.yml + deploy.yml (two independent manual workflows)
CNAME             rulers.ofthepast.org
```

## The harvester

Spine-then-enrich, not merge-of-sources (identical machinery to ROAR). The
orchestrator loads the **spine** (`seed.json`, built by `build_seed.py`) and runs
each **Enricher** in `sources.REGISTRY` over the shared ruler list, in isolation:
a failing enricher is marked `stale` in the manifest and the spine + the other
enrichers survive.

- **Resolution path**: each seed entry carries a curated en.wikipedia title
  (`wp`). `wikipedia.resolve()` maps it to a Wikidata QID; `wikidata.entities()`
  pulls the facts; `wikipedia.extracts()` pulls the biography. All batched.
- **Reign**: `wikidata.reign_years()` is *generalised* for a world roster — it
  takes the widest start/end (P580/P582) across all positions held (P39),
  preferring recognised ruling positions when present. But the **curated seed
  reign wins**: the enricher only fills reign where the seed is blank, and also
  records what Wikidata thought in `reign_wikidata` for auditing.
- Run it: `python -m harvester` (≈ 100 s, ~30 batched API calls). Disable an
  enricher with `OTP_DISABLE=wikipedia` (the ROAR alias `ROAR_DISABLE` also
  works). Re-run `build_seed.py` only if the curated roster itself changes.

Editing the roster = edit `ROSTER` / `REGIONS` / `ERAS` in `build_seed.py`,
re-run it (`python -m harvester.build_seed`), eyeball the contemporaneity
spot-check it prints, then re-harvest.

## Frontend

Plain HTML/CSS/JS, **no build step**, **relative paths only** (custom domain +
any `/staging/` subpath both work). Loads `data/manifest.json` + `data/rulers.json`,
lazy-loads `data/rulers/<id>.json` on medallion click. The **meridian** is the
hero: a year readout over an era-banded rule whose width per era is proportional
to ruler count (navigation, not a data viz — dense ages get room, the sparse
deep past stays compact); the year maps **piecewise-linearly** within its band.
Drag / click / arrow-key the rule, or "let time drift" (a constant-screen-speed
sweep), and the region lanes re-render to whoever was reigning that year. An
"atlas" mode shows everyone; search filters across the whole roster. Theme
persists in localStorage (`otp-theme`). Design is the **synchronic chronicle** —
a cosmographic almanac inked on vellum (light) / under the astral night (dark);
Cormorant + Spectral; gold hairline shared with ROAR; region "inks" and era
"washes" carry meaning and are never fills. Full design context in `.impeccable.md`.

The avatar (`chat.js`, `window.PastChat`) greets in-character and shows a live
"how this avatar is grounded" preview built from the harvested facts; sending a
message POSTs to the shared avatars API (`chat.people.ofthepast.org`), which
rebuilds the same grounding from this atlas's published JSON and answers. If the
backend is unreachable the reply is a self-aware holding message — never invented
history.

## Deploy

**GitHub Pages**, custom domain via `CNAME`. Two independent **manual** workflows
(same discipline as ROAR and the map siblings):

- **Harvest** — re-pull `data/` from Wikidata/Wikipedia, commit to `main`.
  Does *not* publish.
- **Deploy** — stage `web/` + `data/` + `CNAME` → Pages (`actions/deploy-pages`).
  Does *not* harvest. Pages source = "GitHub Actions".

Typical: *frontend change → push → Deploy*; *roster change → edit build_seed.py
and/or augment_seed.py targets → `python -m harvester.augment_seed` → Harvest →
eyeball the manifest → Deploy*.

## House rules

- `data/` is machine-owned harvester output — never hand-edit it.
- The roster lives in `build_seed.py`. That is the one file to edit to add,
  remove, or re-date a ruler; everything downstream is generated.
- No hard-coded credentials. This repo holds no chat key — the model key lives
  only in the shared avatars service (`openfantasymap/avatars`).
- No tests. Don't claim a change is "tested" because nothing broke at import.
- Portraits/biographies are hot-linked from Wikimedia/Wikipedia; keep the credit
  line in the detail panel and footer. The footer always reads
  "Made with <3 in Bologna by OpenHistoryMap" (OHM house line).
- Host runtime is old — run one-off tooling under Docker if the host Python
  chokes (`docker run --rm -v "$PWD":/w -w /w python:3-slim …`).
