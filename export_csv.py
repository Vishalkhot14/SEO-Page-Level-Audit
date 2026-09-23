import csv


def export_csv(audits, filepath, your_index=0, serp_results=None, llm_results=None, primary_kw_results=None):
    serp_results = serp_results or [None] * len(audits)
    llm_results = llm_results or [None] * len(audits)
    primary_kw_results = primary_kw_results or [None] * len(audits)
    fieldnames = [
        "Page", "Role", "Final URL", "Status Code", "Likely Blocked (bot protection)", "Redirect Chain",
        "Title", "Title Length", "Meta Description", "Meta Desc Length",
        "H1 Count", "H1 Text", "H2 Count", "H3 Count", "Heading Issues",
        "Word Count", "Top 5 Keywords (word:count:density%)",
        "Images Total", "Images Missing Alt",
        "Internal Links", "External Links", "Nofollow Outbound Links",
        "Canonical URL", "Canonical Self-Referencing", "Hreflang Tags",
        "Robots Meta", "Viewport Tag Present", "HTML Lang Attr",
        "robots.txt Found", "robots.txt Blocks Page", "Sitemap.xml Found",
        "Schema Types Found", "Schema Blocks Count", "Schema Errors",
        "Mobile PageSpeed Score", "Mobile LCP (ms)", "Mobile CLS", "Mobile FCP (ms)",
        "Domain Authority", "Page Authority", "Backlinks", "Referring Domains", "Nofollow Inbound Links",
        "Primary Keyword", "PK In Title", "PK In H1", "PK In Meta Desc", "PK Headings w/ Keyword", "PK Density %", "PK Instances",
        "SERP Keyword", "SERP Your Position", "SERP Top 5 Competing Titles",
        "LLM Search Intent", "LLM Intent Match", "LLM Top Recommendations",
        "Writer Comments", "Developer Comments",
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, a in enumerate(audits):
            role = "YOUR PAGE" if i == your_index else f"Competitor {i if i < your_index else i}"
            redirect_str = " -> ".join(f'{c["status"]}:{c["url"]}' for c in a.redirect_chain) if a.redirect_chain else ""
            top_kw = "; ".join(f"{w}:{c}:{d}%" for w, c, d in a.top_keywords[:5])
            hreflang_str = "; ".join(f"{code}:{href}" for code, href in a.hreflang_tags)

            pk = primary_kw_results[i] if i < len(primary_kw_results) else None
            if pk:
                pk_keyword = pk["keyword"]
                pk_title = pk["in_title"]
                pk_h1 = pk["in_h1"]
                pk_meta = pk["in_meta"]
                pk_headings = f'{pk["headings_with_kw"]}/{pk["headings_total"]}'
                pk_density = pk["density_pct"]
                pk_instances = pk["instances"]
            else:
                pk_keyword = pk_title = pk_h1 = pk_meta = pk_headings = pk_density = pk_instances = ""

            serp = serp_results[i] if i < len(serp_results) else None
            if serp and serp.get("ok"):
                serp_kw = serp["query"]
                serp_pos = serp["your_position"] if serp["your_position"] else "Not in top 10"
                serp_titles = "; ".join(r["title"] for r in serp["results"][:5])
            elif serp:
                serp_kw = serp.get("query", "")
                serp_pos = f"Error: {serp.get('error','')}"
                serp_titles = ""
            else:
                serp_kw = ""
                serp_pos = ""
                serp_titles = ""

            llm = llm_results[i] if i < len(llm_results) else None
            if llm and llm.get("ok"):
                llm_intent = llm.get("intent", "")
                llm_match = llm.get("intent_match", "")
                llm_recs = llm.get("recommendations", "").replace("\n", " | ")
            elif llm:
                llm_intent = f"Error: {llm.get('error','')}"
                llm_match = ""
                llm_recs = ""
            else:
                llm_intent = ""
                llm_match = ""
                llm_recs = ""
            writer.writerow({
                "Page": a.input_ref,
                "Role": role,
                "Final URL": a.final_url or "",
                "Status Code": a.status_code if a.status_code is not None else ("N/A (local HTML / pasted HTML)" if (a.is_local_html or a.used_html_fallback) else "FETCH FAILED"),
                "Likely Blocked (bot protection)": "YES — treat data below as unreliable" if a.likely_blocked else "No",
                "Redirect Chain": redirect_str,
                "Title": a.title or "MISSING",
                "Title Length": a.title_len,
                "Meta Description": a.meta_description or "MISSING",
                "Meta Desc Length": a.meta_desc_len,
                "H1 Count": len(a.h1_list),
                "H1 Text": " | ".join(a.h1_list),
                "H2 Count": len(a.h2_list),
                "H3 Count": len(a.h3_list),
                "Heading Issues": "; ".join(a.heading_issues),
                "Word Count": a.word_count,
                "Top 5 Keywords (word:count:density%)": top_kw,
                "Images Total": a.images_total,
                "Images Missing Alt": a.images_missing_alt,
                "Internal Links": a.internal_links,
                "External Links": a.external_links,
                "Nofollow Outbound Links": a.nofollow_outbound,
                "Canonical URL": a.canonical or "MISSING",
                "Canonical Self-Referencing": a.canonical_selfref if a.canonical_selfref is not None else "",
                "Hreflang Tags": hreflang_str,
                "Robots Meta": a.robots_meta or "",
                "Viewport Tag Present": bool(a.viewport_tag),
                "HTML Lang Attr": a.lang_attr or "MISSING",
                "robots.txt Found": a.robots_txt_found,
                "robots.txt Blocks Page": a.robots_txt_blocks_page,
                "Sitemap.xml Found": a.sitemap_found,
                "Schema Types Found": "; ".join(a.schema_types_found) if a.schema_types_found else "NONE",
                "Schema Blocks Count": a.schema_raw_count,
                "Schema Errors": "; ".join(a.schema_errors),
                "Mobile PageSpeed Score": a.perf_score_mobile if a.perf_score_mobile is not None else (a.psi_error or "N/A"),
                "Mobile LCP (ms)": a.lcp_mobile or "",
                "Mobile CLS": a.cls_mobile or "",
                "Mobile FCP (ms)": a.fcp_mobile or "",
                "Domain Authority": a.manual_metrics.get("Domain Authority (DA)", ""),
                "Page Authority": a.manual_metrics.get("Page Authority (PA)", ""),
                "Backlinks": a.manual_metrics.get("Backlinks (total)", ""),
                "Referring Domains": a.manual_metrics.get("Referring Domains", ""),
                "Nofollow Inbound Links": a.manual_metrics.get("Nofollow vs Dofollow inbound links", ""),
                "Primary Keyword": pk_keyword,
                "PK In Title": pk_title,
                "PK In H1": pk_h1,
                "PK In Meta Desc": pk_meta,
                "PK Headings w/ Keyword": pk_headings,
                "PK Density %": pk_density,
                "PK Instances": pk_instances,
                "SERP Keyword": serp_kw,
                "SERP Your Position": serp_pos,
                "SERP Top 5 Competing Titles": serp_titles,
                "LLM Search Intent": llm_intent,
                "LLM Intent Match": llm_match,
                "LLM Top Recommendations": llm_recs,
                "Writer Comments": " || ".join(a.writer_comments) if a.writer_comments else "None",
                "Developer Comments": " || ".join(a.dev_comments) if a.dev_comments else "None",
            })
    return filepath
