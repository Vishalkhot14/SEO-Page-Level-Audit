"""
SEO Audit Tool — Core Analyzer
--------------------------------
Fetches each page (or reads local HTML), extracts real on-page, technical,
and schema signals. No fabricated data: anything that can't be measured
for free is explicitly marked as "Manual check needed" with a note on
where to get it.

Author: built for a full on-page/off-page/technical SEO audit across
1 site + up to 5 competitors.
"""

import re
import json
import time
import socket
import urllib.parse as up
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}
TIMEOUT = 20
STOPWORDS = set("""a an the and or but if is are was were be been being of to in on for with
as by at from this that these those it its it's their his her our your you we they i
not no yes do does did have has had will would can could should may might just so than
then there here about into over under again further out up down off above below
get got also one two us using need needs needed dont don doesn isn aren wasn weren
hasn haven hadn wouldn couldn shouldn wont cant more most all any some such only own
same too very s t d ll m re ve www http https com html php net org co uk in
click read learn find know made make many much new used way well even still
back home page pages site sites view viewed today now let lets say says said
please see contact us here now here your our their his her its all""".split())

# Signals that the fetched HTML is an anti-bot / security block page rather
# than real content. If several of these appear alongside a very short page,
# we flag it instead of silently analyzing junk as if it were the real page.
BLOCK_PAGE_SIGNALS = [
    "access denied", "you don't have permission", "you do not have permission",
    "attention required", "cf-browser-verification", "checking your browser",
    "please verify you are a human", "captcha", "request blocked",
    "reference #", "403 forbidden", "the request could not be satisfied",
    "bot detection", "unusual traffic", "automated access",
]


def looks_like_block_page(html_text: str, word_count: int, title: str):
    lowered = (html_text or "").lower()
    hits = [s for s in BLOCK_PAGE_SIGNALS if s in lowered]
    title_lower = (title or "").lower()
    title_is_suspicious = any(s in title_lower for s in ["access denied", "attention required", "just a moment", "403 forbidden", "blocked"])
    if title_is_suspicious:
        return True, hits
    if hits and word_count < 150:
        return True, hits
    return False, hits


@dataclass
class PageAudit:
    input_ref: str
    url: Optional[str] = None
    is_local_html: bool = False
    fetch_ok: bool = False
    fetch_error: Optional[str] = None
    status_code: Optional[int] = None
    redirect_chain: list = field(default_factory=list)
    final_url: Optional[str] = None
    likely_blocked: bool = False
    block_signals: list = field(default_factory=list)
    brand_tokens: set = field(default_factory=set)
    used_html_fallback: bool = False

    # On-page
    title: Optional[str] = None
    title_len: int = 0
    meta_description: Optional[str] = None
    meta_desc_len: int = 0
    h1_list: list = field(default_factory=list)
    h2_list: list = field(default_factory=list)
    h3_list: list = field(default_factory=list)
    heading_outline_ok: bool = True
    heading_issues: list = field(default_factory=list)
    word_count: int = 0
    top_keywords: list = field(default_factory=list)  # (word, count, density%) - single words
    top_phrases: list = field(default_factory=list)   # (phrase, count) - real 1-4 word phrases
    heading_phrases: set = field(default_factory=set)  # phrases found specifically inside H1/H2/H3
    body_text_lower: str = ""  # cached for primary-keyword density lookups
    images_total: int = 0
    images_missing_alt: int = 0
    internal_links: int = 0
    external_links: int = 0
    nofollow_outbound: int = 0

    # Technical
    canonical: Optional[str] = None
    canonical_selfref: Optional[bool] = None
    hreflang_tags: list = field(default_factory=list)
    robots_meta: Optional[str] = None
    viewport_tag: Optional[str] = None
    is_https: bool = False
    lang_attr: Optional[str] = None
    robots_txt_found: Optional[bool] = None
    robots_txt_blocks_page: Optional[bool] = None
    sitemap_found: Optional[bool] = None
    sitemap_url: Optional[str] = None

    # Schema
    schema_types_found: list = field(default_factory=list)
    schema_raw_count: int = 0
    schema_errors: list = field(default_factory=list)

  # PageSpeed / CWV
    psi_ok: bool = False
    psi_error: Optional[str] = None
    perf_score_mobile: Optional[int] = None
    lcp_mobile: Optional[float] = None
    cls_mobile: Optional[float] = None
    inp_mobile: Optional[float] = None
    fcp_mobile: Optional[float] = None

    # Comments
    writer_comments: list = field(default_factory=list)
    dev_comments: list = field(default_factory=list)

    # Manual-only off-page metrics (never fabricated)
    manual_metrics: dict = field(default_factory=dict)


def fetch(url: str):
    """Fetch a URL, following redirects, recording the chain and status codes."""
    chain = []
    try:
        session = requests.Session()
        resp = session.get(url, headers=REQUEST_HEADERS, timeout=TIMEOUT, allow_redirects=True)
        for h in resp.history:
            chain.append({"url": h.url, "status": h.status_code})
        return resp, chain, None
    except requests.exceptions.SSLError as e:
        return None, chain, f"SSL error: {e}"
    except requests.exceptions.ConnectionError as e:
        return None, chain, f"Connection error: {e}"
    except requests.exceptions.Timeout:
        return None, chain, "Timed out"
    except Exception as e:
        return None, chain, str(e)


def check_robots_txt(base_url: str, target_path: str):
    """Real robots.txt fetch + a simple disallow check (not a full parser, but honest)."""
    parsed = up.urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        r = requests.get(robots_url, headers=REQUEST_HEADERS, timeout=10)
        if r.status_code != 200:
            return False, None, robots_url
        lines = r.text.splitlines()
        blocked = False
        applies = False
        for line in lines:
            line = line.strip()
            if line.lower().startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip()
                applies = agent == "*"
            elif applies and line.lower().startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if path and target_path.startswith(path):
                    blocked = True
        return True, blocked, robots_url
    except Exception:
        return False, None, robots_url


def check_sitemap(base_url: str):
    parsed = up.urlparse(base_url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    try:
        r = requests.get(sitemap_url, headers=REQUEST_HEADERS, timeout=10)
        return (r.status_code == 200), sitemap_url
    except Exception:
        return False, sitemap_url


def extract_keywords(text: str, top_n=15):
    raw_words = re.findall(r"[a-zA-Z']{3,}", text.lower())
    words = []
    for w in raw_words:
        normalized = w.replace("'", "")  # "don't" -> "dont", matches STOPWORDS
        if normalized in STOPWORDS:
            continue
        if normalized.isdigit() or len(normalized) < 3:
            continue
        words.append(normalized)
    total = len(words)
    if total == 0:
        return []
    counts = Counter(words).most_common(top_n)
    return [(w, c, round(c / total * 100, 2)) for w, c in counts]


def extract_phrases(text: str, max_words=4, top_n=25):
    """
    Real multi-word phrase extraction (RAKE-lite): splits text into runs of
    consecutive non-stopword words, and treats each run (chunked to at most
    max_words) as a candidate phrase. This produces meaningful terms like
    "travel insurance" or "medical expenses" instead of fragmented single
    words like "cover" or "loss" with no context.
    """
    # Sentence/tag punctuation and newlines are hard boundaries — a run of
    # words must never bridge across a period, comma, or block-tag break,
    # or phrases end up stitching unrelated sentences together.
    BOUNDARY = "\x01"
    marked = re.sub(r"[\.\!\?\;\:\,\(\)\[\]\{\}\"\n\r/|]+", f" {BOUNDARY} ", text)
    tokens = re.findall(r"[A-Za-z']+|\x01", marked.lower())
    runs = []
    current = []
    for tok in tokens:
        if tok == BOUNDARY:
            if current:
                runs.append(current)
                current = []
            continue
        norm = tok.replace("'", "")
        if norm in STOPWORDS or len(norm) < 3 or norm.isdigit():
            if current:
                runs.append(current)
                current = []
        else:
            current.append(norm)
    if current:
        runs.append(current)

    phrase_counter = Counter()
    for run in runs:
        for i in range(0, len(run), max_words):
            chunk = run[i:i + max_words]
            if chunk:
                phrase_counter[" ".join(chunk)] += 1
    return phrase_counter.most_common(top_n)


def analyze_schema(soup: BeautifulSoup):
    types_found = []
    errors = []
    scripts = soup.find_all("script", type="application/ld+json")
    for s in scripts:
        raw = s.string or s.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    t = item.get("@type")
                    if t:
                        types_found.append(t if isinstance(t, str) else ",".join(t))
                    if "@graph" in item and isinstance(item["@graph"], list):
                        for g in item["@graph"]:
                            if isinstance(g, dict) and g.get("@type"):
                                gt = g["@type"]
                                types_found.append(gt if isinstance(gt, str) else ",".join(gt))
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON-LD: {e}")
    # also check microdata itemtype as a fallback signal
    microdata = soup.find_all(attrs={"itemtype": True})
    for m in microdata:
        itemtype = m.get("itemtype", "")
        name = itemtype.rstrip("/").split("/")[-1]
        if name:
            types_found.append(f"{name} (microdata)")
    return types_found, len(scripts), errors


def check_heading_outline(h1s, h2s, h3s):
    issues = []
    if len(h1s) == 0:
        issues.append("No H1 found on the page.")
    elif len(h1s) > 1:
        issues.append(f"{len(h1s)} H1 tags found — should be exactly one.")
    if len(h1s) >= 1 and len(h2s) == 0 and len(h3s) > 0:
        issues.append("H3s present but no H2s — heading hierarchy skips a level.")
    return (len(issues) == 0), issues


def analyze_page(ref: str, is_url: bool, psi_api_key: Optional[str] = None, html_override: Optional[str] = None,
                  html_fallback: Optional[str] = None) -> PageAudit:
    """
    ref: the URL (if is_url=True) or a local file path / raw HTML string (if is_url=False)
    html_override: for local-HTML mode, the actual HTML content to analyze
    html_fallback: OPTIONAL — raw HTML you paste yourself (e.g. via view-source in your
                   browser) to use INSTEAD of a live fetch, when a URL is blocked, requires
                   login, or otherwise can't be crawled normally. If provided alongside a
                   URL, live technical checks (status code, redirects, robots.txt, sitemap,
                   PageSpeed) are skipped since there's no live response to check — but
                   on-page/schema/content analysis runs on your pasted HTML instead of
                   silently analyzing a block page.
    """
    audit = PageAudit(input_ref=ref, is_local_html=not is_url)

    if is_url and html_fallback:
        # User-supplied HTML overrides a live fetch entirely for this page.
        audit.url = ref
        html = html_fallback
        audit.fetch_ok = True
        audit.status_code = None
        audit.final_url = ref
        audit.used_html_fallback = True
        audit.dev_comments.append(
            "This page was analyzed from HTML you pasted manually (html_fallback), not a live "
            "fetch — status code, redirects, robots.txt, sitemap.xml, and Page Speed checks are "
            "skipped since there's no live response for them."
        )
    elif is_url:
        audit.url = ref
        resp, chain, err = fetch(ref)
        audit.redirect_chain = chain
        if err or resp is None:
            audit.fetch_ok = False
            audit.fetch_error = err
            audit.dev_comments.append(f"Fetch failed: {err}. Check the URL is correct and publicly reachable, or supply html_fallback for this page.")
            return audit
        audit.fetch_ok = True
        audit.status_code = resp.status_code
        audit.final_url = resp.url
        audit.is_https = resp.url.startswith("https://")
        html = resp.text
        if resp.status_code >= 400:
            audit.dev_comments.append(f"Page returned HTTP {resp.status_code}. Fix the broken URL or add a proper redirect.")
        if chain:
            codes = " -> ".join(str(c["status"]) for c in chain) + f" -> {resp.status_code}"
            audit.dev_comments.append(f"Redirect chain detected ({codes}). Update internal links to point directly to the final URL to avoid link equity loss.")
    else:
        audit.url = ref
        html = html_override if html_override is not None else ref
        audit.fetch_ok = True
        audit.status_code = None
        audit.final_url = None

    soup = BeautifulSoup(html, "lxml")

    # --- Title ---
    title_tag = soup.find("title")
    audit.title = title_tag.get_text(strip=True) if title_tag else None
    audit.title_len = len(audit.title) if audit.title else 0
    if not audit.title:
        audit.writer_comments.append("Missing <title> tag — add a unique, keyword-relevant title (50-60 characters).")
        audit.dev_comments.append("No <title> element found in <head>.")
    elif audit.title_len < 30:
        audit.writer_comments.append(f"Title is short ({audit.title_len} chars). Consider expanding toward 50-60 characters to use available SERP space.")
    elif audit.title_len > 60:
        audit.writer_comments.append(f"Title is long ({audit.title_len} chars) and may get truncated in search results. Trim toward 50-60 characters.")

    # --- Meta description ---
    meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    audit.meta_description = meta_desc.get("content", "").strip() if meta_desc else None
    audit.meta_desc_len = len(audit.meta_description) if audit.meta_description else 0
    if not audit.meta_description:
        audit.writer_comments.append("Missing meta description — add one (~140-160 characters) summarizing the page to improve SERP click-through.")
        audit.dev_comments.append('No <meta name="description"> tag found.')
    elif audit.meta_desc_len < 70:
        audit.writer_comments.append(f"Meta description is short ({audit.meta_desc_len} chars). Aim for 140-160 characters.")
    elif audit.meta_desc_len > 160:
        audit.writer_comments.append(f"Meta description is long ({audit.meta_desc_len} chars) and may be truncated. Trim toward 155 characters.")

    # --- Headings ---
    audit.h1_list = [h.get_text(strip=True) for h in soup.find_all("h1")]
    audit.h2_list = [h.get_text(strip=True) for h in soup.find_all("h2")]
    audit.h3_list = [h.get_text(strip=True) for h in soup.find_all("h3")]
    ok, issues = check_heading_outline(audit.h1_list, audit.h2_list, audit.h3_list)
    audit.heading_outline_ok = ok
    audit.heading_issues = issues
    for issue in issues:
        audit.writer_comments.append(f"Heading structure: {issue}")
        audit.dev_comments.append(f"Heading structure: {issue}")

    # --- Schema (must run BEFORE script tags are stripped for word count) ---
    types_found, raw_count, schema_errors = analyze_schema(soup)
    audit.schema_types_found = types_found
    audit.schema_raw_count = raw_count
    audit.schema_errors = schema_errors
    if raw_count == 0:
        audit.dev_comments.append("No structured data (JSON-LD) found. Consider adding schema markup (Organization, BreadcrumbList, Article/Product/FAQPage as relevant) to enable rich results.")
        audit.writer_comments.append("No schema markup detected — structured data can help this page qualify for rich snippets in search results.")
    if schema_errors:
        for e in schema_errors:
            audit.dev_comments.append(f"Schema error: {e}")

    # --- Body text / word count / keyword density ---
    for tag in soup(["script", "style", "noscript", "title"]):
        tag.decompose()
    # separator="\n" (not " ") so block-level tags don't run into each other
    # with no boundary — e.g. an H1 immediately followed by a paragraph would
    # otherwise merge into one fake phrase during extraction.
    body_text = soup.get_text(separator="\n", strip=True)
    audit.word_count = len(body_text.split())

    # --- Block-page detection (must run before we trust anything else) ---
    blocked, signals = looks_like_block_page(html, audit.word_count, audit.title)
    audit.likely_blocked = blocked
    audit.block_signals = signals
    if blocked:
        audit.dev_comments.append(
            "This response looks like an anti-bot / security block page (Cloudflare, WAF, "
            "or similar), not the site's real content — signals found: " + ", ".join(signals[:3]) +
            ". Every metric below reflects the BLOCK PAGE, not the actual page. Fixes: try again "
            "later, use a different network, or use the html_fallback option to paste the page's "
            "real HTML (copy via view-source in your browser) instead of fetching it live."
        )
        audit.writer_comments.append(
            "Heads up: this page could not be fetched normally — it was blocked by the site's bot "
            "protection. The content shown here is not real; treat this page's results as unreliable "
            "until re-run with a pasted HTML fallback."
        )

    audit.top_keywords = extract_keywords(body_text, top_n=15)
    audit.top_phrases = extract_phrases(body_text, max_words=4, top_n=25)
    audit.body_text_lower = body_text.lower()
    heading_text = " . ".join(audit.h1_list + audit.h2_list + audit.h3_list)
    audit.heading_phrases = set(p for p, c in extract_phrases(heading_text, max_words=4, top_n=50))
    if audit.word_count < 300 and not blocked:
        audit.writer_comments.append(f"Thin content: only {audit.word_count} words. Pages competing for informational queries typically need substantially more depth.")

    # --- Brand tokens for this page's own domain (used to keep gap analysis honest) ---
    domain_source = audit.final_url or (ref if is_url else "")
    if domain_source:
        netloc = up.urlparse(domain_source).netloc.replace("www.", "")
        domain_root = netloc.split(".")[0] if netloc else ""
        if domain_root:
            audit.brand_tokens = {domain_root.lower()}

    # --- Images / alt text ---
    imgs = soup.find_all("img")
    audit.images_total = len(imgs)
    audit.images_missing_alt = sum(1 for i in imgs if not i.get("alt", "").strip())
    if audit.images_missing_alt > 0:
        audit.writer_comments.append(f"{audit.images_missing_alt} of {audit.images_total} images are missing descriptive alt text.")
        audit.dev_comments.append(f'{audit.images_missing_alt} <img> tags missing alt="" attributes — add descriptive alt text for accessibility and image SEO.')

    # --- Links ---
    base_netloc = up.urlparse(audit.final_url or (ref if is_url else "")).netloc
    internal = external = nofollow = 0
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:") or href.startswith("javascript:"):
            continue
        rel = a.get("rel", [])
        is_nofollow = "nofollow" in rel if isinstance(rel, list) else "nofollow" in str(rel)
        if href.startswith("http"):
            link_netloc = up.urlparse(href).netloc
            if base_netloc and link_netloc == base_netloc:
                internal += 1
            else:
                external += 1
                if is_nofollow:
                    nofollow += 1
        else:
            internal += 1
    audit.internal_links = internal
    audit.external_links = external
    audit.nofollow_outbound = nofollow
    if internal < 2:
        audit.writer_comments.append("Very few internal links found. Add contextual links to related pages to strengthen internal linking and crawl paths.")

    # --- Canonical / hreflang / robots meta / viewport / lang ---
    canon = soup.find("link", rel=lambda v: v and "canonical" in v)
    audit.canonical = canon.get("href") if canon else None
    if audit.canonical and audit.final_url:
        audit.canonical_selfref = up.urlparse(audit.canonical).path.rstrip("/") == up.urlparse(audit.final_url).path.rstrip("/")
    if not audit.canonical:
        audit.dev_comments.append("No canonical tag found — add <link rel='canonical'> to prevent duplicate-content issues.")
    elif audit.canonical_selfref is False:
        audit.dev_comments.append(f"Canonical tag points to a different URL ({audit.canonical}) than the page served. Confirm this is intentional.")

    hreflangs = soup.find_all("link", rel="alternate", hreflang=True)
    audit.hreflang_tags = [(h.get("hreflang"), h.get("href")) for h in hreflangs]

    robots_meta = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    audit.robots_meta = robots_meta.get("content") if robots_meta else None
    if audit.robots_meta and ("noindex" in audit.robots_meta.lower()):
        audit.dev_comments.append(f"Page has a robots meta tag with 'noindex' ({audit.robots_meta}) — confirm this is intentional; it blocks indexing.")

    viewport = soup.find("meta", attrs={"name": "viewport"})
    audit.viewport_tag = viewport.get("content") if viewport else None
    if not audit.viewport_tag:
        audit.dev_comments.append("No mobile viewport meta tag found — add <meta name='viewport' content='width=device-width, initial-scale=1'>.")

    html_tag = soup.find("html")
    audit.lang_attr = html_tag.get("lang") if html_tag else None
    if not audit.lang_attr:
        audit.dev_comments.append("Missing lang attribute on <html> tag.")

    # --- robots.txt & sitemap (only for live URLs) ---
    if is_url and audit.final_url and not audit.used_html_fallback:
        found, blocked, robots_url = check_robots_txt(audit.final_url, up.urlparse(audit.final_url).path)
        audit.robots_txt_found = found
        audit.robots_txt_blocks_page = blocked
        if blocked:
            audit.dev_comments.append(f"robots.txt ({robots_url}) appears to disallow this page's path — verify crawlers aren't blocked unintentionally.")
        sm_found, sm_url = check_sitemap(audit.final_url)
        audit.sitemap_found = sm_found
        audit.sitemap_url = sm_url
        if not sm_found:
            audit.dev_comments.append(f"No sitemap.xml found at {sm_url}. Add one and submit it in Google Search Console.")

    # --- Manual-only metrics, explicitly flagged, never fabricated ---
    audit.manual_metrics = {
        "Domain Authority (DA)": "Manual check needed — Moz Link Explorer (free, limited lookups/month): https://moz.com/link-explorer",
        "Page Authority (PA)": "Manual check needed — same Moz tool as above.",
        "Backlinks (total)": "Manual check needed — Google Search Console (free, your own site only) or Ahrefs/Semrush free backlink checker (limited results) for competitors.",
        "Referring Domains": "Manual check needed — same sources as Backlinks.",
        "Nofollow vs Dofollow inbound links": "Manual check needed — not derivable from on-page crawl; requires a backlink index (Ahrefs/Semrush/Moz).",
    }

    # --- PageSpeed Insights (mobile) — only for live URLs ---
    if is_url and audit.final_url and not audit.used_html_fallback:
        run_psi(audit, audit.final_url, psi_api_key)

    return audit


def analyze_primary_keyword(audit: PageAudit, keyword: str):
    """
    Checks whether a target/primary keyword appears where it should: title,
    H1, meta description, headings — plus real density in the body text.
    Returns None if no keyword was given (feature is fully optional).
    """
    if not keyword or not keyword.strip():
        return None
    kw = keyword.strip().lower()
    kw_word_count = len(kw.split())

    title_l = (audit.title or "").lower()
    h1_text = " ".join(audit.h1_list).lower()
    meta_l = (audit.meta_description or "").lower()
    headings_all = audit.h1_list + audit.h2_list + audit.h3_list
    headings_with_kw = [h for h in headings_all if kw in h.lower()]

    instances = audit.body_text_lower.count(kw) if audit.body_text_lower else 0
    density_pct = round((instances * kw_word_count) / audit.word_count * 100, 2) if audit.word_count else 0.0

    return {
        "keyword": keyword,
        "in_title": kw in title_l,
        "in_h1": kw in h1_text,
        "in_meta": kw in meta_l,
        "headings_with_kw": len(headings_with_kw),
        "headings_total": len(headings_all),
        "matching_headings": headings_with_kw[:3],
        "instances": instances,
        "density_pct": density_pct,
    }


def run_psi(audit: PageAudit, url: str, api_key: Optional[str]):
    endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params = {"url": url, "strategy": "mobile", "category": "PERFORMANCE"}
    if api_key:
        params["key"] = api_key
    try:
        r = requests.get(endpoint, params=params, timeout=60)
        if r.status_code != 200:
            audit.psi_ok = False
            audit.psi_error = f"HTTP {r.status_code}: {r.text[:200]}"
            return
        data = r.json()
        lr = data.get("lighthouseResult", {})
        cats = lr.get("categories", {})
        perf = cats.get("performance", {})
        audit.perf_score_mobile = round(perf.get("score", 0) * 100) if perf.get("score") is not None else None
        audits = lr.get("audits", {})
        def metric(key):
            v = audits.get(key, {}).get("numericValue")
            return round(v, 1) if v is not None else None
        audit.lcp_mobile = metric("largest-contentful-paint")
        audit.cls_mobile = audits.get("cumulative-layout-shift", {}).get("numericValue")
        audit.inp_mobile = metric("interactive")
        audit.fcp_mobile = metric("first-contentful-paint")
        audit.psi_ok = True
        if audit.perf_score_mobile is not None and audit.perf_score_mobile < 50:
            audit.dev_comments.append(f"Mobile PageSpeed performance score is low ({audit.perf_score_mobile}/100). Investigate render-blocking resources, image sizes, and server response time.")
    except Exception as e:
        audit.psi_ok = False
        audit.psi_error = str(e)
