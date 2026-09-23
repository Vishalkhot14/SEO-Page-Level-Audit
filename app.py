"""
SEO Audit Tool — Streamlit Web App
------------------------------------
A real website: URL text boxes, drag-and-drop HTML upload, buttons, and
downloadable results. No code editing required to use it.

Run locally with:  streamlit run app.py
Deploy free at:     share.streamlit.io (see DEPLOY.md for steps)
"""

import time
import streamlit as st

from analyzer import analyze_page, analyze_primary_keyword
from content_gap import build_content_gap
from export_csv import export_csv
from export_dashboard import build_dashboard
from serp_analysis import analyze_serp_for_keyword
from llm_analysis import run_llm_analysis

st.set_page_config(page_title="SEO Audit Tool", layout="wide")

st.title("SEO Audit Tool")
st.caption(
    "Audit your page against up to 5 competitors — on-page, technical, schema, "
    "Page Speed, content gaps, and more. Free, real data — nothing fabricated."
)

LABELS = ["Your Page", "Competitor 1", "Competitor 2", "Competitor 3", "Competitor 4", "Competitor 5"]

st.markdown("### 1. Add your pages")
st.caption("Your page + at least one competitor are required. The rest are optional.")

page_inputs = []
for i, label in enumerate(LABELS):
    required = i < 2
    with st.expander(f"{label}" + ("  •  required" if required else "  •  optional"), expanded=required):
        input_type = st.radio(
            "How do you want to give this page?",
            ["URL", "Upload HTML file", "Paste HTML"],
            key=f"type_{i}", horizontal=True,
        )
        value, html_content = None, None
        if input_type == "URL":
            value = st.text_input("Page URL", key=f"url_{i}", placeholder="https://example.com/page")
        elif input_type == "Upload HTML file":
            uploaded = st.file_uploader("Drag & drop or browse for an .html file", type=["html", "htm"], key=f"upload_{i}")
            if uploaded is not None:
                html_content = uploaded.read().decode("utf-8", errors="ignore")
                value = uploaded.name
        else:
            html_content = st.text_area("Paste the page's HTML source", key=f"paste_{i}", height=150,
                                         placeholder="View Page Source in your browser, then Ctrl+A / Ctrl+C, paste here")
            if html_content:
                value = f"{label.lower().replace(' ', '-')}-pasted"
        keyword = st.text_input("Target keyword for this page (optional — enables Primary Keyword & SERP checks)", key=f"kw_{i}")
        page_inputs.append({"input_type": input_type, "value": value, "html_content": html_content, "keyword": keyword})

st.markdown("### 2. Optional: free API keys")
with st.expander("Page Speed / Google SERP / LLM keys — all optional, tool works without them"):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**PageSpeed Insights** (free)")
        psi_key = st.text_input("PSI API key", type="password", key="psi_key",
                                 help="developers.google.com/speed/docs/insights/v5/get-started")
        st.markdown("**Google Custom Search** (free, 100/day)")
        cse_key = st.text_input("Google CSE API key", type="password", key="cse_key")
        cse_cx = st.text_input("Google CSE Search Engine ID (cx)", key="cse_cx")
    with col_b:
        st.markdown("**LLM analysis** (your own key, small real cost)")
        llm_provider = st.selectbox("Provider", ["None", "anthropic", "openai", "gemini"], key="llm_provider")
        llm_key = st.text_input("LLM API key", type="password", key="llm_key") if llm_provider != "None" else None
        if llm_provider in ("openai", "gemini"):
            st.caption("⚠ Only 'anthropic' is tested in this build — openai/gemini are real but unverified implementations.")

run = st.button("Run Audit", type="primary", use_container_width=True)

if run:
    filled = [p for p in page_inputs if p["value"]]
    if len(filled) < 2:
        st.error("Add at least your page + 1 competitor before running.")
    else:
        progress = st.progress(0.0)
        status = st.empty()
        log_box = st.container()

        audits, serp_results, llm_results, primary_kw_results, keywords_list = [], [], [], [], []
        total = len([p for p in page_inputs if p["value"]])
        done = 0

        for idx, p in enumerate(page_inputs):
            if not p["value"]:
                continue
            label = LABELS[idx]
            display_val = p["value"] if len(p["value"]) < 70 else p["value"][:70] + "..."
            status.write(f"Analyzing **{label}**: {display_val} ...")

            if p["input_type"] == "URL":
                audit = analyze_page(p["value"], is_url=True, psi_api_key=psi_key or None)
            else:
                audit = analyze_page(p["value"], is_url=False, html_override=p["html_content"] or "")

            if audit.likely_blocked:
                log_box.warning(f"⚠ {label}: looks like a bot-protection block page, not real content. "
                                 f"Re-run using 'Paste HTML' for this page instead.")
            elif audit.fetch_ok:
                log_box.write(f"✅ {label}: {audit.word_count} words, {len(audit.schema_types_found)} schema types found")
            else:
                log_box.error(f"❌ {label}: fetch failed — {audit.fetch_error}")

            audits.append(audit)
            keywords_list.append(p["keyword"])

            pk = analyze_primary_keyword(audit, p["keyword"]) if p["keyword"] else None
            primary_kw_results.append(pk)

            serp = None
            if p["keyword"] and cse_key and cse_cx:
                serp = analyze_serp_for_keyword(p["keyword"], cse_key, cse_cx, your_url=audit.final_url or audit.url)
            serp_results.append(serp)

            llm = None
            if llm_provider != "None" and llm_key:
                llm = run_llm_analysis(audit, llm_provider, llm_key, None, serp_context=serp)
            llm_results.append(llm)

            done += 1
            progress.progress(done / total)
            time.sleep(0.2)

        status.write("Building content gap analysis and reports...")
        gap_data = build_content_gap(audits, your_index=0)

        csv_path = "/tmp/audit.csv"
        dash_path = "/tmp/dashboard.html"
        export_csv(audits, csv_path, your_index=0, serp_results=serp_results, llm_results=llm_results, primary_kw_results=primary_kw_results)
        build_dashboard(audits, gap_data, your_index=0, filepath=dash_path, serp_results=serp_results,
                         llm_results=llm_results, keywords=keywords_list, primary_kw_results=primary_kw_results)

        status.write("Done.")
        progress.progress(1.0)
        st.success("Audit complete — download or preview your results below.")

        with open(dash_path, "r", encoding="utf-8") as f:
            dash_html = f.read()
        with open(csv_path, "rb") as f:
            csv_bytes = f.read()

        col1, col2 = st.columns(2)
        with col1:
            st.download_button("⬇ Download dashboard.html", dash_html, file_name="dashboard.html",
                                mime="text/html", use_container_width=True)
        with col2:
            st.download_button("⬇ Download audit.csv", csv_bytes, file_name="audit.csv",
                                mime="text/csv", use_container_width=True)

        st.markdown("### Preview")
        st.iframe(dash_html, height=1400)

st.divider()
st.caption(
    "This tool never fabricates data. Domain Authority, Page Authority, backlinks, and "
    "referring domains require a paid backlink index (Ahrefs/Semrush/Moz) — see the "
    "Off-Page section of your results for free manual-check links instead of a guessed number."
)
