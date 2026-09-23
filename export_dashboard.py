import html
import json


def _esc(s):
    if s is None:
        return ""
    return html.escape(str(s))


def _status_pill(ok, label_ok="OK", label_bad="Issue"):
    cls = "pill-ok" if ok else "pill-bad"
    label = label_ok if ok else label_bad
    return f'<span class="pill {cls}">{label}</span>'


def build_dashboard(audits, gap_data, your_index, filepath, serp_results=None, llm_results=None, keywords=None, primary_kw_results=None):
    n = len(audits)
    serp_results = serp_results or [None] * n
    llm_results = llm_results or [None] * n
    keywords = keywords or [""] * n
    primary_kw_results = primary_kw_results or [None] * n
    role_names = []
    for i in range(n):
        role_names.append("Your Page" if i == your_index else f"Competitor {i if i < your_index else i}")

    # ---------- Summary scorecards ----------
    def score_row(a):
        checks = [
            bool(a.title),
            bool(a.meta_description),
            len(a.h1_list) == 1,
            bool(a.canonical),
            a.images_missing_alt == 0 if a.images_total > 0 else True,
            a.schema_raw_count > 0,
            bool(a.viewport_tag),
            (a.perf_score_mobile or 0) >= 50 if a.perf_score_mobile is not None else True,
        ]
        return sum(checks), len(checks)

    scorecards = ""
    for i, a in enumerate(audits):
        highlight = " your-card" if i == your_index else ""
        if a.likely_blocked:
            scorecards += f"""
        <div class="score-card{highlight}">
          <div class="score-card-role">{_esc(role_names[i])}</div>
          <div class="score-card-ref">{_esc(a.input_ref[:60])}</div>
          <div class="score-ring" style="--pct:0; --ring-color:#b3382c">
            <span>⚠</span>
          </div>
          <div class="score-sub flag-bad">Blocked — not real content</div>
        </div>"""
            continue
        passed, total = score_row(a)
        pct = round(passed / total * 100)
        color = "#2e7d5b" if pct >= 75 else ("#b8860b" if pct >= 50 else "#b3382c")
        scorecards += f"""
        <div class="score-card{highlight}">
          <div class="score-card-role">{_esc(role_names[i])}</div>
          <div class="score-card-ref">{_esc(a.input_ref[:60])}</div>
          <div class="score-ring" style="--pct:{pct}; --ring-color:{color}">
            <span>{pct}%</span>
          </div>
          <div class="score-sub">{passed}/{total} checks passed</div>
        </div>"""

    # ---------- On-page comparison table ----------
    def onpage_row(label, getter, kind="text"):
        cells = ""
        for a in audits:
            val = getter(a)
            cells += f"<td>{val}</td>"
        return f"<tr><th>{label}</th>{cells}</tr>"

    onpage_rows = ""
    onpage_rows += onpage_row("Title", lambda a: f'{_esc(a.title) or "<span class=\"flag-bad\">MISSING</span>"} <span class=\"muted\">({a.title_len} chars)</span>')
    onpage_rows += onpage_row("Meta Description", lambda a: f'{_esc((a.meta_description or "")[:80])}{"..." if a.meta_description and len(a.meta_description) > 80 else ""}' if a.meta_description else '<span class="flag-bad">MISSING</span>')
    onpage_rows += onpage_row("H1", lambda a: (f'{len(a.h1_list)} tag(s): "{_esc(a.h1_list[0][:50])}"' if a.h1_list else '<span class="flag-bad">MISSING</span>') + ('' if len(a.h1_list) == 1 else ' <span class="flag-bad">⚠ should be 1</span>'))
    onpage_rows += onpage_row("H2 / H3 count", lambda a: f"{len(a.h2_list)} / {len(a.h3_list)}")
    onpage_rows += onpage_row("Word Count", lambda a: f'{a.word_count}' + (' <span class="flag-bad">thin</span>' if a.word_count < 300 else ''))
    onpage_rows += onpage_row("Images (missing alt)", lambda a: f'{a.images_total} ({a.images_missing_alt} missing)' + (' <span class="flag-bad">⚠</span>' if a.images_missing_alt else ''))
    onpage_rows += onpage_row("Internal / External Links", lambda a: f"{a.internal_links} / {a.external_links}")
    onpage_rows += onpage_row("Nofollow Outbound", lambda a: str(a.nofollow_outbound))

    # ---------- Technical table ----------
    tech_rows = ""
    tech_rows += onpage_row("HTTP Status", lambda a: (
        (f'{a.status_code} <span class="flag-bad">⚠ BLOCKED — bot protection, not real content</span>' if a.likely_blocked else str(a.status_code))
        if a.status_code else ("Local file" if a.is_local_html else '<span class="flag-bad">FETCH FAILED</span>')
    ))
    tech_rows += onpage_row("Redirect Chain", lambda a: (" → ".join(str(c["status"]) for c in a.redirect_chain) + f" → {a.status_code}") if a.redirect_chain else "None")
    tech_rows += onpage_row("HTTPS", lambda a: "Yes" if a.is_https else ('<span class="flag-bad">No</span>' if a.url and a.url.startswith("http") else "N/A"))
    tech_rows += onpage_row("Canonical Tag", lambda a: _esc((a.canonical or "")[:60]) if a.canonical else '<span class="flag-bad">MISSING</span>')
    tech_rows += onpage_row("Hreflang Tags", lambda a: f"{len(a.hreflang_tags)} found" if a.hreflang_tags else "None")
    tech_rows += onpage_row("Robots Meta", lambda a: _esc(a.robots_meta) if a.robots_meta else "Default (indexable)")
    tech_rows += onpage_row("Mobile Viewport", lambda a: "Present" if a.viewport_tag else '<span class="flag-bad">MISSING</span>')
    tech_rows += onpage_row("robots.txt", lambda a: ("Found" + (" — blocks this page ⚠" if a.robots_txt_blocks_page else "")) if a.robots_txt_found else ("Not checked (local file)" if a.is_local_html else '<span class="flag-bad">Not found</span>'))
    tech_rows += onpage_row("sitemap.xml", lambda a: "Found" if a.sitemap_found else ("Not checked (local file)" if a.is_local_html else '<span class="flag-bad">Not found</span>'))

    # ---------- Schema table ----------
    schema_rows = ""
    schema_rows += onpage_row("Schema Types Found", lambda a: ", ".join(a.schema_types_found) if a.schema_types_found else '<span class="flag-bad">None</span>')
    schema_rows += onpage_row("JSON-LD Blocks", lambda a: str(a.schema_raw_count))
    schema_rows += onpage_row("Schema Errors", lambda a: "; ".join(a.schema_errors) if a.schema_errors else "None")

    # ---------- PageSpeed table ----------
    psi_rows = ""
    psi_rows += onpage_row("Mobile Performance Score", lambda a: (f'{a.perf_score_mobile}/100' if a.perf_score_mobile is not None else (_esc(a.psi_error) if a.psi_error else "N/A (local file)")))
    psi_rows += onpage_row("LCP (Largest Contentful Paint)", lambda a: f"{a.lcp_mobile} ms" if a.lcp_mobile else "—")
    psi_rows += onpage_row("CLS (Cumulative Layout Shift)", lambda a: f"{a.cls_mobile}" if a.cls_mobile is not None else "—")
    psi_rows += onpage_row("FCP (First Contentful Paint)", lambda a: f"{a.fcp_mobile} ms" if a.fcp_mobile else "—")

    # ---------- Off-page (manual) ----------
    manual_keys = ["Domain Authority (DA)", "Page Authority (PA)", "Backlinks (total)", "Referring Domains", "Nofollow vs Dofollow inbound links"]
    manual_rows = ""
    for key in manual_keys:
        manual_rows += f'<tr><th>{_esc(key)}</th><td colspan="{n}" class="manual-note">{_esc(audits[0].manual_metrics.get(key, ""))}</td></tr>'

    # ---------- Header row (page identifiers) ----------
    header_cells = ""
    for i, a in enumerate(audits):
        cls = ' class="your-col"' if i == your_index else ""
        header_cells += f'<th{cls}>{_esc(role_names[i])}<br><span class="muted small">{_esc(a.input_ref[:40])}</span></th>'

    # ---------- Content gap section ----------
    gap_keywords_html = ""
    for item in gap_data.get("missing_phrases", [])[:15]:
        where = f'used in a <strong>heading</strong> by {item["in_heading_count"]} of them' if item["in_heading_count"] > 0 else "found in body copy only"
        gap_keywords_html += f'<li><strong>"{_esc(item["phrase"])}"</strong> — used by {item["competitor_count"]} competitor page(s); {where}</li>'
    if not gap_keywords_html:
        gap_keywords_html = "<li>No major phrase gaps detected.</li>"

    gap_headings_html = ""
    for h in gap_data.get("missing_headings", [])[:15]:
        gap_headings_html += f'<li>"{_esc(h)}" — a real competitor heading with no equivalent section on your page</li>'
    if not gap_headings_html:
        gap_headings_html = "<li>No major heading-topic gaps detected.</li>"

    # ---------- Comments sections ----------
    # Full "fix this" action items only make sense for YOUR page — nobody
    # needs step-by-step instructions for fixing a competitor's site. For
    # competitors we show a compact issue-count benchmark instead.
    your_audit = audits[your_index]
    your_w_items = "".join(f"<li>{_esc(c)}</li>" for c in your_audit.writer_comments) or "<li>No writer-facing issues found.</li>"
    your_d_items = "".join(f"<li>{_esc(c)}</li>" for c in your_audit.dev_comments) or "<li>No developer-facing issues found.</li>"
    blocked_banner = ""
    if your_audit.likely_blocked:
        blocked_banner = '<p class="manual-note">This page could not be fetched cleanly (see Technical SEO section) — the items below may reflect a block page, not your real content.</p>'
    comments_html = f"""
        <div class="comment-block">
          <h4>{_esc(role_names[your_index])} <span class="muted small">{_esc(your_audit.input_ref[:60])}</span></h4>
          {blocked_banner}
          <div class="comment-cols">
            <div><h5>For the Writer</h5><ul>{your_w_items}</ul></div>
            <div><h5>For the Developer</h5><ul>{your_d_items}</ul></div>
          </div>
        </div>"""

    competitor_rows = ""
    for i, a in enumerate(audits):
        if i == your_index:
            continue
        status = "Blocked / could not fetch cleanly" if a.likely_blocked else "Fetched OK"
        competitor_rows += f"""<tr>
          <td>{_esc(role_names[i])}<br><span class="muted small">{_esc(a.input_ref[:50])}</span></td>
          <td>{status}</td>
          <td>{len(a.writer_comments)}</td>
          <td>{len(a.dev_comments)}</td>
        </tr>"""
    competitor_benchmark_html = f"""
        <div class="comment-block">
          <h4>Competitor Benchmark <span class="muted small">(for comparison only — not action items on their behalf)</span></h4>
          <div class="table-scroll">
          <table>
            <thead><tr><th>Page</th><th>Fetch Status</th><th># Writer-side issues found</th><th># Dev-side issues found</th></tr></thead>
            <tbody>{competitor_rows}</tbody>
          </table>
          </div>
          <p class="muted small" style="margin-top:10px;">Full detail for these is in the On-Page / Technical / Schema tables above if you want to dig into what a competitor is doing differently.</p>
        </div>"""

    # ---------- Primary Keyword Alignment section ----------
    any_pk_configured = any(pk is not None for pk in primary_kw_results)
    pk_section_html = ""
    if any_pk_configured:
        rows = ""
        for i, pk in enumerate(primary_kw_results):
            if pk is None:
                rows += f'<tr><td>{_esc(role_names[i])}</td><td colspan="6" class="muted small">No target keyword set for this page.</td></tr>'
                continue
            title_pill = _status_pill(pk["in_title"])
            h1_pill = _status_pill(pk["in_h1"])
            meta_pill = _status_pill(pk["in_meta"])
            heading_ratio = f'{pk["headings_with_kw"]}/{pk["headings_total"]}'
            heading_cls = "flag-bad" if pk["headings_with_kw"] == 0 and pk["headings_total"] > 0 else ""
            density_cls = "flag-bad" if pk["density_pct"] == 0 else ""
            rows += f"""<tr>
              <td>{_esc(role_names[i])}<br><span class="muted small">"{_esc(pk["keyword"])}"</span></td>
              <td>{title_pill}</td>
              <td>{h1_pill}</td>
              <td>{meta_pill}</td>
              <td class="{heading_cls}">{heading_ratio}</td>
              <td class="{density_cls}">{pk["density_pct"]}%</td>
              <td>{pk["instances"]}</td>
            </tr>"""
        pk_section_html = f"""
  <section>
    <h2>Primary Keyword Alignment</h2>
    <div class="note-box">Checks whether each page's target keyword actually appears where it needs to — title, H1, meta description, headings — plus real density in the body text. A missing H1/heading match or 0% density is a real, fixable gap.</div>
    <div class="table-scroll">
    <table>
      <thead><tr><th>Page / Keyword</th><th>In Title</th><th>In H1</th><th>In Meta Desc</th><th>Headings w/ Keyword</th><th>Density</th><th>Instances</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
  </section>"""

    # ---------- SERP section ----------
    any_serp_configured = any(s is not None for s in serp_results)
    serp_section_html = ""
    if any_serp_configured:
        blocks = ""
        for i, s in enumerate(serp_results):
            if s is None:
                continue
            kw = _esc(s.get("query", keywords[i] if i < len(keywords) else ""))
            if s.get("ok"):
                pos = s.get("your_position")
                pos_html = f'<span class="pill pill-ok">Position {pos}</span>' if pos else '<span class="pill pill-bad">Not in top 10</span>'
                rows = ""
                for r in s["results"][:10]:
                    rows += f'<tr><td>{r["position"]}</td><td>{_esc(r["title"])}</td><td class="muted small">{_esc(r["displayLink"])}</td><td class="small">{_esc(r["snippet"][:120])}</td></tr>'
                blocks += f"""
                <div class="comment-block">
                  <h4>{_esc(role_names[i])} — keyword: "{kw}" {pos_html}</h4>
                  <div class="table-scroll">
                  <table><thead><tr><th>#</th><th>Title</th><th>Domain</th><th>Snippet</th></tr></thead>
                  <tbody>{rows}</tbody></table>
                  </div>
                </div>"""
            else:
                blocks += f"""
                <div class="comment-block">
                  <h4>{_esc(role_names[i])} — keyword: "{kw}"</h4>
                  <p class="manual-note">{_esc(s.get("error",""))}</p>
                </div>"""
        serp_section_html = f"""
  <section>
    <h2>Google SERP Snapshot</h2>
    <div class="note-box">Source: Google Custom Search JSON API (free tier, 100 queries/day). Shows real top-ranking titles/snippets — not AI Overviews or PAA boxes, which have no API.</div>
    {blocks}
  </section>"""

    # ---------- LLM section ----------
    any_llm_configured = any(l is not None for l in llm_results)
    llm_section_html = ""
    if any_llm_configured:
        blocks = ""
        for i, l in enumerate(llm_results):
            if l is None:
                continue
            if l.get("ok"):
                recs_escaped = _esc(l.get("recommendations", "")).replace("\n", "<br>")
                blocks += f"""
                <div class="comment-block">
                  <h4>{_esc(role_names[i])}</h4>
                  <p><strong>Search intent:</strong> {_esc(l.get("intent",""))}</p>
                  <p><strong>Intent match:</strong> {_esc(l.get("intent_match",""))}</p>
                  <p><strong>Top recommendations:</strong><br>{recs_escaped}</p>
                </div>"""
            else:
                blocks += f"""
                <div class="comment-block">
                  <h4>{_esc(role_names[i])}</h4>
                  <p class="manual-note">{_esc(l.get("error",""))}</p>
                </div>"""
        llm_section_html = f"""
  <section>
    <h2>AI-Generated Intent &amp; Recommendations</h2>
    <div class="note-box">Generated by an LLM reasoning over this page's real crawled data (and SERP context where available). This is qualitative judgment, not a measured metric — treat it as a second opinion, not ground truth.</div>
    {blocks}
  </section>"""

    now_str = ""
    try:
        import datetime
        now_str = datetime.datetime.now().strftime("%d %b %Y, %H:%M")
    except Exception:
        pass

    template = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SEO Audit Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --ink: #1c2321;
    --paper: #fbfaf7;
    --line: #d8d4c8;
    --accent: #2f5d50;
    --accent-2: #a8763e;
    --bad: #b3382c;
    --good: #2e7d5b;
    --warn: #b8860b;
    --mono: 'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace;
    --serif: 'Source Serif 4', 'Georgia', serif;
    --sans: 'Inter', -apple-system, sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: var(--sans);
    line-height: 1.5;
  }}
  header.top {{
    padding: 40px 32px 28px;
    border-bottom: 2px solid var(--ink);
    background: var(--paper);
  }}
  header.top h1 {{
    font-family: var(--serif);
    font-size: 2.1rem;
    margin: 0 0 6px;
    font-weight: 600;
    letter-spacing: -0.01em;
  }}
  header.top p {{ margin: 0; color: #55564f; font-size: 0.95rem; }}
  .container {{ max-width: 1180px; margin: 0 auto; padding: 0 32px 80px; }}
  section {{ margin-top: 48px; }}
  section > h2 {{
    font-family: var(--serif);
    font-size: 1.4rem;
    border-bottom: 1px solid var(--line);
    padding-bottom: 10px;
    margin-bottom: 20px;
  }}
  .scorecards {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .score-card {{
    border: 1px solid var(--line);
    background: #fff;
    padding: 18px;
    flex: 1 1 160px;
    min-width: 160px;
    text-align: center;
  }}
  .score-card.your-card {{ border: 2px solid var(--accent); }}
  .score-card-role {{ font-weight: 600; font-size: 0.85rem; letter-spacing: 0.02em; }}
  .score-card-ref {{ font-size: 0.72rem; color: #777; margin: 2px 0 12px; word-break: break-all; }}
  .score-ring {{
    width: 72px; height: 72px; border-radius: 50%; margin: 0 auto 10px;
    display: flex; align-items: center; justify-content: center;
    background: conic-gradient(var(--ring-color) calc(var(--pct) * 1%), #eae7dd 0);
    font-weight: 600; font-size: 0.95rem; position: relative;
  }}
  .score-ring::before {{
    content: ""; position: absolute; width: 54px; height: 54px; border-radius: 50%; background: #fff;
  }}
  .score-ring span {{ position: relative; z-index: 1; }}
  .score-sub {{ font-size: 0.78rem; color: #666; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 0.86rem; }}
  th, td {{ border: 1px solid var(--line); padding: 10px 12px; text-align: left; vertical-align: top; }}
  thead th {{ background: #f1efe6; font-weight: 600; }}
  tbody th {{ width: 200px; background: #f8f7f2; font-weight: 600; color: #333; }}
  th.your-col {{ background: #e6efe9; }}
  .muted {{ color: #888; }}
  .small {{ font-size: 0.75rem; }}
  .flag-bad {{ color: var(--bad); font-weight: 600; }}
  .manual-note {{ font-style: italic; color: #6b5a3a; background: #fbf6ea; font-size: 0.82rem; }}
  .pill {{ display: inline-block; padding: 2px 9px; border-radius: 3px; font-size: 0.75rem; font-weight: 600; }}
  .pill-ok {{ background: #e2f1e8; color: var(--good); }}
  .pill-bad {{ background: #fbe6e2; color: var(--bad); }}
  .table-scroll {{ overflow-x: auto; }}
  .gap-cols {{ display: flex; gap: 32px; flex-wrap: wrap; }}
  .gap-cols > div {{ flex: 1 1 320px; background: #fff; border: 1px solid var(--line); padding: 18px 20px; }}
  .gap-cols h3 {{ font-family: var(--serif); font-size: 1.05rem; margin-top: 0; }}
  .gap-cols ul {{ margin: 0; padding-left: 20px; font-size: 0.87rem; }}
  .gap-cols li {{ margin-bottom: 6px; }}
  .comment-block {{ border: 1px solid var(--line); background: #fff; padding: 18px 20px; margin-bottom: 18px; }}
  .comment-block h4 {{ margin: 0 0 12px; font-family: var(--serif); font-size: 1.05rem; }}
  .comment-cols {{ display: flex; gap: 28px; flex-wrap: wrap; }}
  .comment-cols > div {{ flex: 1 1 260px; }}
  .comment-cols h5 {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--accent-2); margin: 0 0 8px; }}
  .comment-cols ul {{ margin: 0; padding-left: 18px; font-size: 0.86rem; }}
  .comment-cols li {{ margin-bottom: 7px; }}
  .note-box {{
    border-left: 3px solid var(--accent-2);
    background: #fbf6ea;
    padding: 14px 18px;
    font-size: 0.88rem;
    margin-bottom: 24px;
  }}
  footer {{ text-align: center; color: #999; font-size: 0.78rem; padding: 30px 0 10px; }}
</style>
</head>
<body>
<header class="top">
  <h1>SEO Audit Dashboard</h1>
  <p>{n} pages analyzed — generated {_esc(now_str)}. All figures below were pulled live from each page; nothing is estimated.</p>
</header>
<div class="container">

  <section>
    <h2>Overall Health Scorecard</h2>
    <div class="scorecards">{scorecards}</div>
  </section>

  <section>
    <h2>On-Page SEO</h2>
    <div class="table-scroll">
    <table>
      <thead><tr><th></th>{header_cells}</tr></thead>
      <tbody>{onpage_rows}</tbody>
    </table>
    </div>
  </section>

  <section>
    <h2>Technical SEO</h2>
    <div class="table-scroll">
    <table>
      <thead><tr><th></th>{header_cells}</tr></thead>
      <tbody>{tech_rows}</tbody>
    </table>
    </div>
  </section>

  <section>
    <h2>Schema / Structured Data</h2>
    <div class="table-scroll">
    <table>
      <thead><tr><th></th>{header_cells}</tr></thead>
      <tbody>{schema_rows}</tbody>
    </table>
    </div>
  </section>

  <section>
    <h2>Page Speed &amp; Core Web Vitals (Mobile)</h2>
    <div class="note-box">Source: Google PageSpeed Insights API (free, public). If a row shows an error instead of a score, PSI's public rate limit was likely hit — get a free key and re-run (instructions in the README).</div>
    <div class="table-scroll">
    <table>
      <thead><tr><th></th>{header_cells}</tr></thead>
      <tbody>{psi_rows}</tbody>
    </table>
    </div>
  </section>

  <section>
    <h2>Off-Page (Backlinks / Authority)</h2>
    <div class="note-box">These metrics require a paid backlink index (Ahrefs, Semrush, Moz) for full accuracy. No free API gives reliable DA/PA or full backlink counts — anything shown here as a number would be a guess, so we don't show one. Use the free-tier links below for a partial manual check.</div>
    <div class="table-scroll">
    <table>
      <tbody>{manual_rows}</tbody>
    </table>
    </div>
  </section>

  <section>
    <h2>Content Gap Analysis (Yours vs Competitors)</h2>
    <div class="gap-cols">
      <div>
        <h3>Real phrases competitors use that you don't</h3>
        <ul>{gap_keywords_html}</ul>
      </div>
      <div>
        <h3>Whole competitor headings you have no equivalent for</h3>
        <ul>{gap_headings_html}</ul>
      </div>
    </div>
  </section>

{pk_section_html}

{serp_section_html}

{llm_section_html}

  <section>
    <h2>Action Items — Writer &amp; Developer Comments</h2>
    <div class="note-box">Detailed fix-it recommendations are shown only for your own page. Competitor data below is a benchmark for comparison, not advice on their behalf.</div>
    {comments_html}
    {competitor_benchmark_html}
  </section>

</div>
<footer>Generated by your reusable local SEO Audit Tool. Re-run anytime on any URLs — no subscription, no API cost for on-page/technical/schema/speed checks.</footer>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(template)
    return filepath
