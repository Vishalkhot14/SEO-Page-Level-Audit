"""
SERP Analysis — Google Programmable Search Engine (Custom Search JSON API)
----------------------------------------------------------------------------
This is the ONLY free, official, ToS-compliant way to get real Google
search results programmatically. Free tier: 100 queries/day.

It does NOT give you: true ranking position tracking beyond top ~10-100,
AI Overview presence/content, People Also Ask boxes, or SERP feature
layout — Google does not expose any of that via any API, free or paid.
What it DOES give you: real titles, snippets, and URLs of top-ranking
pages for a query, which is enough to see who you're actually competing
with and how their titles/snippets are angled.

Setup (free, ~5 minutes):
1. Create a Programmable Search Engine: https://programmablesearchengine.google.com/
   - Set it to "Search the entire web"
   - Copy the Search Engine ID (cx)
2. Get an API key: https://developers.google.com/custom-search/v1/introduction
   - Click "Get a Key" (free tier: 100 queries/day, no billing required)
3. Paste both into run_audit.py (GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX)

If you skip this setup, SERP analysis is simply omitted from the report —
no fake results are ever shown.
"""

import requests

CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


def fetch_serp(query, api_key, cx, num=10):
    """
    Returns a dict: {"ok": bool, "results": [...], "error": str|None}
    Each result: {"position": int, "title": str, "link": str, "snippet": str, "displayLink": str}
    """
    if not api_key or not cx:
        return {"ok": False, "results": [], "error": "No Google CSE API key / CX configured — SERP analysis skipped."}

    params = {"key": api_key, "cx": cx, "q": query, "num": min(num, 10)}
    try:
        r = requests.get(CSE_ENDPOINT, params=params, timeout=20)
        if r.status_code == 429:
            return {"ok": False, "results": [], "error": "Free daily quota (100 queries/day) exceeded. Try again tomorrow, or reduce keyword count."}
        if r.status_code != 200:
            return {"ok": False, "results": [], "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        data = r.json()
        items = data.get("items", [])
        results = []
        for i, item in enumerate(items, start=1):
            results.append({
                "position": i,
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "displayLink": item.get("displayLink", ""),
            })
        return {"ok": True, "results": results, "error": None}
    except Exception as e:
        return {"ok": False, "results": [], "error": str(e)}


def find_page_position(serp_results, target_url):
    """Check if target_url (or its domain) appears in the SERP results."""
    from urllib.parse import urlparse
    target_netloc = urlparse(target_url).netloc.replace("www.", "")
    for r in serp_results:
        r_netloc = urlparse(r["link"]).netloc.replace("www.", "")
        if r_netloc == target_netloc:
            return r["position"], r["link"]
    return None, None


def analyze_serp_for_keyword(query, api_key, cx, your_url=None):
    """
    Full SERP analysis for one keyword: fetch results, find your position
    (if your_url given), and summarize what's ranking.
    """
    serp = fetch_serp(query, api_key, cx)
    result = {
        "query": query,
        "ok": serp["ok"],
        "error": serp["error"],
        "results": serp["results"],
        "your_position": None,
        "your_matched_url": None,
    }
    if serp["ok"] and your_url:
        pos, matched = find_page_position(serp["results"], your_url)
        result["your_position"] = pos
        result["your_matched_url"] = matched
    return result
