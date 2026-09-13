"""
Shared LLM client used by Module 1 (change detection) and Module 3
(fix generation).

Provider priority, all free-tier friendly:
  1. OPENROUTER_API_KEY set -> OpenRouter (defaults to the "openrouter/free"
     router, which auto-picks a free model - no card required)
  2. GROQ_API_KEY set        -> Groq (llama-3.3-70b-versatile) - free tier, no card required
  3. GEMINI_API_KEY set      -> Google Gemini (gemini-2.0-flash) - free tier, no card required
  4. ANTHROPIC_API_KEY set   -> Claude (paid) - kept for anyone who does have a key
  5. none set                -> returns None, caller falls back to frozen mock output

Every provider is called with a single (prompt, max_tokens) call so
detect_changes.py and generate_fix.py don't need to know which provider
is active.
"""

import os
import requests

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"
# "openrouter/free" auto-picks a currently-available free model for you,
# so this doesn't break when OpenRouter rotates its free model lineup.
# Override with OPENROUTER_MODEL in .env if you want a specific one instead,
# e.g. "deepseek/deepseek-v4-flash:free" or "moonshotai/kimi-k2.6:free".
OPENROUTER_DEFAULT_MODEL = "openrouter/free"


def _call_openrouter(prompt: str, max_tokens: int) -> str:
    api_key = os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("OPENROUTER_MODEL", OPENROUTER_DEFAULT_MODEL)
    print(f"[openrouter] key starts with: {api_key[:12]}... | model: {model}")
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/",
            "X-Title": "API Change Agent"
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0
        },
        timeout=30
    )
    if not resp.ok:
        print(f"[openrouter] FAILED {resp.status_code}: {resp.text}")
        raise RuntimeError(f"OpenRouter {resp.status_code}: {resp.text}")
    data = resp.json()
    if "choices" not in data:
        raise RuntimeError(f"OpenRouter error: {data}")
    content = data["choices"][0]["message"]["content"]
    if not content or not content.strip():
        raise RuntimeError(f"OpenRouter returned empty content. Full response: {data}")
    return content.strip()
    
def _call_groq(prompt: str, max_tokens: int) -> str:
    api_key = os.environ["GROQ_API_KEY"]
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0
        },
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_gemini(prompt: str, max_tokens: int) -> str:
    api_key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    resp = requests.post(
        url,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0}
        },
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_anthropic(prompt: str, max_tokens: int) -> str:
    from anthropic import Anthropic
    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()


def active_provider() -> str:
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "mock"


def call_llm(prompt: str, max_tokens: int = 500) -> str | None:
    """Returns the raw text response, or None if no provider is configured
    (in which case the caller should use its frozen mock output)."""
    provider = active_provider()
    if provider == "openrouter":
        return _call_openrouter(prompt, max_tokens)
    if provider == "groq":
        return _call_groq(prompt, max_tokens)
    if provider == "gemini":
        return _call_gemini(prompt, max_tokens)
    if provider == "anthropic":
        return _call_anthropic(prompt, max_tokens)
    return None


def clean_json_text(text: str) -> str:
    """Strip markdown code fences some models wrap JSON in."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip().rstrip("`").strip()