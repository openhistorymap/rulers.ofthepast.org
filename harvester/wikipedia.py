"""Minimal English-Wikipedia (MediaWiki Action API) client.

Two batched calls are all the harvester needs:
  - `resolve(titles)` — map each requested title to its canonical page and the
    page's Wikidata QID (`pageprops.wikibase_item`), following normalisation and
    redirects. 50 titles per request.
  - `extracts(titles)` — lead-section plain-text extract + lead image + short
    description + canonical URL. 20 titles per request (the API caps `extracts`
    at 20 when `exintro` is combined with multiple titles).

Both follow MediaWiki etiquette: a descriptive User-Agent with a contact URL,
polite pacing, and a maxlag guard so we back off when the cluster is busy.
"""

import time

import requests

API_URL = "https://en.wikipedia.org/w/api.php"
UA = "rulers.ofancientrome.org/1.0 (https://github.com/openhistorymap/rulers.ofancientrome.org; OpenHistoryMap)"


def _api(params, attempts=4, http_timeout=60):
    params = {**params, "format": "json", "formatversion": "2", "maxlag": "5"}
    last = None
    for i in range(attempts):
        try:
            r = requests.get(
                API_URL, params=params, headers={"User-Agent": UA}, timeout=http_timeout
            )
            if r.status_code in (429, 503):
                last = f"HTTP {r.status_code}"
                time.sleep(10 + 10 * i)
                continue
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("error", {}).get("code") == "maxlag":
                last = "maxlag"
                time.sleep(8 + 5 * i)
                continue
            return data
        except requests.RequestException as e:
            last = repr(e)
            time.sleep(5 + 5 * i)
    raise RuntimeError(f"wikipedia request failed: {last}")


def _redirect_resolver(query):
    """Build a function mapping a requested title to the final page title,
    chaining the API's `normalized` and `redirects` remaps."""
    remap = {}
    for n in query.get("normalized", []) or []:
        remap[n["from"]] = n["to"]
    for rd in query.get("redirects", []) or []:
        remap[rd["from"]] = rd["to"]

    def final(title):
        seen = set()
        cur = title
        while cur in remap and cur not in seen:
            seen.add(cur)
            cur = remap[cur]
        return cur

    return final


def resolve(titles, chunk=50):
    """{requested_title: {'qid': str|None, 'title': final_title, 'missing': bool}}"""
    out = {}
    titles = list(dict.fromkeys(titles))
    for i in range(0, len(titles), chunk):
        batch = titles[i : i + chunk]
        data = _api({
            "action": "query",
            "redirects": "1",
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "titles": "|".join(batch),
        })
        q = data.get("query", {})
        final = _redirect_resolver(q)
        pages = {p.get("title"): p for p in q.get("pages", [])}
        for t in batch:
            page = pages.get(final(t), {})
            out[t] = {
                "title": page.get("title", final(t)),
                "qid": (page.get("pageprops") or {}).get("wikibase_item"),
                "missing": bool(page.get("missing", False)),
            }
        time.sleep(1)
    return out


def extracts(titles, chunk=20, thumbsize=800):
    """{requested_title: {extract, description, thumbnail, original, url}}"""
    out = {}
    titles = list(dict.fromkeys(titles))
    for i in range(0, len(titles), chunk):
        batch = titles[i : i + chunk]
        data = _api({
            "action": "query",
            "redirects": "1",
            "prop": "extracts|pageimages|description|info",
            "inprop": "url",
            "exintro": "1",
            "explaintext": "1",
            "piprop": "thumbnail|original",
            "pithumbsize": str(thumbsize),
            "titles": "|".join(batch),
        })
        q = data.get("query", {})
        final = _redirect_resolver(q)
        pages = {p.get("title"): p for p in q.get("pages", [])}
        for t in batch:
            page = pages.get(final(t), {})
            out[t] = {
                "title": page.get("title"),
                "extract": page.get("extract"),
                "description": page.get("description"),
                "thumbnail": (page.get("thumbnail") or {}).get("source"),
                "original": (page.get("original") or {}).get("source"),
                "url": page.get("fullurl") or page.get("canonicalurl"),
            }
        time.sleep(1)
    return out
