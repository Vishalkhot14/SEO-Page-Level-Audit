"""
Content Gap Analysis
---------------------
Compares real multi-word phrases (not fragmented single words) between your
page and competitors, and tags WHERE each phrase was found — in a heading
(H1/H2/H3) or only in body copy — so the gap list is actually actionable.

Excludes: any competitor's own brand/domain name, and any page flagged as
a bot-block page (its "content" isn't real).
"""

from collections import Counter


def build_content_gap(audits, your_index=0):
    all_brand_tokens = set()
    for a in audits:
        all_brand_tokens |= getattr(a, "brand_tokens", set())

    usable_audits = [a for a in audits if not getattr(a, "likely_blocked", False)]
    excluded_blocked_pages = [a.input_ref for a in audits if getattr(a, "likely_blocked", False)]

    if your_index >= len(audits) or getattr(audits[your_index], "likely_blocked", False):
        return {
            "missing_phrases": [],
            "missing_headings": [],
            "your_word_count": audits[your_index].word_count if your_index < len(audits) else 0,
            "competitor_word_counts": [],
            "excluded_blocked_pages": excluded_blocked_pages,
            "your_page_blocked": True,
        }

    your_audit = audits[your_index]
    competitor_audits = [a for a in usable_audits if a is not your_audit]

    def phrase_contains_brand(phrase):
        words = set(phrase.split())
        return bool(words & all_brand_tokens)

    your_phrase_set = set(p for p, c in your_audit.top_phrases)

    # phrase -> {"competitor_count": n, "in_heading_count": n}
    phrase_info = {}
    for a in competitor_audits:
        seen_this_page = set()
        for phrase, count in a.top_phrases:
            if phrase_contains_brand(phrase) or phrase in your_phrase_set:
                continue
            if phrase in seen_this_page:
                continue
            seen_this_page.add(phrase)
            info = phrase_info.setdefault(phrase, {"competitor_count": 0, "in_heading_count": 0})
            info["competitor_count"] += 1
            if phrase in a.heading_phrases:
                info["in_heading_count"] += 1

    missing_phrases = []
    for phrase, info in sorted(
        phrase_info.items(),
        key=lambda kv: (-kv[1]["competitor_count"], -kv[1]["in_heading_count"], -len(kv[0].split()))
    ):
        missing_phrases.append({
            "phrase": phrase,
            "competitor_count": info["competitor_count"],
            "in_heading_count": info["in_heading_count"],
        })

    # --- Heading-level gap: literal heading strings competitors have that
    # you don't cover (word-overlap check, not exact match, to avoid noise
    # from trivial phrasing differences) ---
    def normalize_heading(h):
        return set(w for w in h.lower().split() if len(w) > 2)

    your_heading_word_sets = [normalize_heading(h) for h in (your_audit.h2_list + your_audit.h3_list)]

    def heading_covered(comp_heading_words):
        if not comp_heading_words:
            return True
        for your_words in your_heading_word_sets:
            if not your_words:
                continue
            overlap = len(comp_heading_words & your_words) / len(comp_heading_words)
            if overlap >= 0.6:
                return True
        return False

    missing_headings = []
    seen_heading_text = set()
    for a in competitor_audits:
        for h in (a.h2_list + a.h3_list):
            h_clean = h.strip()
            if not h_clean or h_clean.lower() in seen_heading_text:
                continue
            words = normalize_heading(h_clean)
            if words & all_brand_tokens:
                continue
            if len(words) < 2:
                continue
            if not heading_covered(words):
                missing_headings.append(h_clean)
                seen_heading_text.add(h_clean.lower())

    return {
        "missing_phrases": missing_phrases[:20],
        "missing_headings": missing_headings[:15],
        "your_word_count": your_audit.word_count,
        "competitor_word_counts": [(a.input_ref, a.word_count) for a in competitor_audits],
        "excluded_blocked_pages": excluded_blocked_pages,
        "your_page_blocked": False,
    }
