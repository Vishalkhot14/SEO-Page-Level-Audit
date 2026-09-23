"""
LLM Analysis — Search Intent, Content Recommendations, SERP-based insights
------------------------------------------------------------------------------
IMPORTANT HONESTY NOTE:
This tool ships with a WORKING integration for Anthropic's Claude API only,
because that's the one API key mechanism available to build and test here.

"Support" for OpenAI (GPT) / Google (Gemini) / others is provided as
clearly-labeled, honestly-empty slots below (see PROVIDER CONFIG). If you
have your own API key for one of those, paste it in and flip the
LLM_PROVIDER setting — the call function for each is a real, correct
implementation of that provider's chat-completions API, but it has NOT
been tested against a live key (I don't have one to test with). Claude's
path IS tested and working.

None of these are free in the "zero cost" sense — LLM API calls cost
fractions of a cent each per page. This is not a scraping/free-tier trick;
it's real usage-based API pricing. Expect well under $0.05 total for a
6-page audit with Claude Haiku-class pricing.

If you don't want to spend anything on LLM calls, set LLM_PROVIDER = None
in run_audit.py and this entire section is skipped — the rest of the
tool (on-page/technical/schema/speed/SERP) works exactly the same without it.
"""

import json
import requests

# ============================================================
# PROVIDER CONFIG — only "anthropic" is tested/working here.
# Others are real API implementations, untested (no key available
# in this environment). Use at your own key's cost/risk.
# ============================================================

ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
GEMINI_ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _build_prompt(audit, serp_context=None):
    schema_str = ", ".join(audit.schema_types_found) if audit.schema_types_found else "None"
    top_kw = ", ".join(w for w, c, d in audit.top_keywords[:10])
    serp_block = ""
    if serp_context and serp_context.get("ok"):
        titles = "\n".join(f"- {r['title']} ({r['displayLink']})" for r in serp_context["results"][:5])
        serp_block = f"\n\nTop 5 competing results currently ranking for a likely target query:\n{titles}"

    prompt = f"""You are an experienced SEO strategist reviewing one page. Be concise, specific, and honest — if the page is fine, say so briefly rather than inventing problems.

PAGE DATA:
- Title: {audit.title or "MISSING"}
- Meta description: {audit.meta_description or "MISSING"}
- H1: {audit.h1_list[0] if audit.h1_list else "MISSING"}
- H2s: {", ".join(audit.h2_list[:8]) if audit.h2_list else "None"}
- Word count: {audit.word_count}
- Top keywords in content: {top_kw or "none extracted"}
- Schema types present: {schema_str}
{serp_block}

Answer in this exact structure, plain text, no markdown headers:

INTENT: (one line — what search intent does this page's content actually serve: informational, commercial, transactional, or navigational, and why)
INTENT MATCH: (one line — does the title/H1/content align with that intent, or is there a mismatch worth fixing)
TOP 3 RECOMMENDATIONS: (three short, specific, actionable bullets — not generic advice like "improve content quality")
"""
    return prompt


def call_claude(prompt, model="claude-sonnet-4-6", max_tokens=500):
    try:
        resp = requests.post(
            ANTHROPIC_ENDPOINT,
            headers={
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
                # api key injected by caller via env/config — see run_audit.py
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return None, f"Claude API error {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return text.strip(), None
    except Exception as e:
        return None, str(e)


def call_claude_with_key(prompt, api_key, model="claude-sonnet-4-6", max_tokens=500):
    try:
        resp = requests.post(
            ANTHROPIC_ENDPOINT,
            headers={
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": api_key,
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return None, f"Claude API error {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return text.strip(), None
    except Exception as e:
        return None, str(e)


def call_openai_with_key(prompt, api_key, model="gpt-4o-mini", max_tokens=500):
    """
    Real implementation of OpenAI's chat completions API. NOT tested live
    (no key available in the build environment) — implementation follows
    OpenAI's documented API shape as of early 2026, but verify on first run.
    """
    try:
        resp = requests.post(
            OPENAI_ENDPOINT,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return None, f"OpenAI API error {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return text.strip(), None
    except Exception as e:
        return None, str(e)


def call_gemini_with_key(prompt, api_key, model="gemini-1.5-flash"):
    """
    Real implementation of Google's Gemini generateContent API. NOT tested
    live (no key available in the build environment) — verify on first run.
    """
    try:
        url = GEMINI_ENDPOINT_TEMPLATE.format(model=model)
        resp = requests.post(
            url,
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=60,
        )
        if resp.status_code != 200:
            return None, f"Gemini API error {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text.strip(), None
    except Exception as e:
        return None, str(e)


def parse_structured_response(text):
    """Pull the three labeled fields out of the LLM's plain-text response."""
    result = {"intent": "", "intent_match": "", "recommendations": ""}
    if not text:
        return result
    lines = text.split("\n")
    current = None
    buf = {"INTENT:": "intent", "INTENT MATCH:": "intent_match", "TOP 3 RECOMMENDATIONS:": "recommendations"}
    for line in lines:
        stripped = line.strip()
        matched_key = None
        for label, key in buf.items():
            if stripped.upper().startswith(label):
                matched_key = key
                stripped = stripped[len(label):].strip()
                break
        if matched_key:
            current = matched_key
            result[current] = stripped
        elif current:
            result[current] += ("\n" + stripped if stripped else "")
    return result


def run_llm_analysis(audit, provider, api_key, model, serp_context=None):
    """
    Returns dict: {"ok": bool, "error": str|None, "intent": str,
                   "intent_match": str, "recommendations": str}
    """
    if not provider or not api_key:
        return {"ok": False, "error": "LLM analysis not configured (no provider/key set) — skipped.",
                "intent": "", "intent_match": "", "recommendations": ""}

    prompt = _build_prompt(audit, serp_context)

    if provider == "anthropic":
        text, err = call_claude_with_key(prompt, api_key, model=model or "claude-sonnet-4-6")
    elif provider == "openai":
        text, err = call_openai_with_key(prompt, api_key, model=model or "gpt-4o-mini")
    elif provider == "gemini":
        text, err = call_gemini_with_key(prompt, api_key, model=model or "gemini-1.5-flash")
    else:
        return {"ok": False, "error": f"Unknown provider '{provider}'.",
                "intent": "", "intent_match": "", "recommendations": ""}

    if err:
        return {"ok": False, "error": err, "intent": "", "intent_match": "", "recommendations": ""}

    parsed = parse_structured_response(text)
    return {"ok": True, "error": None, **parsed}
