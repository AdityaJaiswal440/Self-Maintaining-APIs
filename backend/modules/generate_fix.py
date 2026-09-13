"""
Module 3: Fix Generation

For each affected call site, produce a minimal, targeted code diff -
never a full-file rewrite. The prompt is deliberately constrained to only
touch the specific call and its immediate arguments, because an
untrustworthy diff is worse than no diff at all in this product.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # lets this run standalone too
from modules.llm_client import call_llm, active_provider

DEMO_REPO_PATH = Path(__file__).parent.parent / "demo_repo"

FIX_PROMPT_TEMPLATE = """You are a precise code-fixing engine. You will be given:
1. A snippet of Python code containing a Stripe API call site.
2. A description of what needs to change and why.

Produce ONLY the corrected version of the snippet. Do not change anything
outside of what the migration note describes. Do not add comments,
explanations, or markdown fences. Preserve exact indentation and style.

Original snippet:
---
{ORIGINAL_SNIPPET}
---

Migration note: {MIGRATION_NOTE}
Old pattern: {OLD_PATTERN}
New pattern: {NEW_PATTERN}

Return only the corrected snippet.
"""

# Frozen outputs for MOCK mode - these were produced by actually running
# this prompt once, same principle as Module 1's mock data.
MOCK_FIXES = {
    "charges-to-payment-intents": '''    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency=currency,
        payment_method=token,
        confirm=True,
        description="Order checkout payment"
    )
    return intent''',
    "source-param-removed": '''    intent = stripe.PaymentIntent.confirm(
        payment_intent_id,
        payment_method=source_id
    )
    return intent'''
}


def _get_snippet(file_name: str, line_no: int, context: int = 6) -> str:
    """Grab a few lines around the call site for context."""
    lines = (DEMO_REPO_PATH / file_name).read_text().splitlines()
    start = max(0, line_no - 2)
    end = min(len(lines), line_no + context)
    return "\n".join(lines[start:end])


def _call_llm_for_fix(snippet: str, migration_note: str, old_pattern: str, new_pattern: str) -> str:
    prompt = FIX_PROMPT_TEMPLATE.format(
        ORIGINAL_SNIPPET=snippet,
        MIGRATION_NOTE=migration_note,
        OLD_PATTERN=old_pattern,
        NEW_PATTERN=new_pattern
    )
    return call_llm(prompt, max_tokens=700)


def generate_fixes(matched_sites: list[dict]) -> list[dict]:
    """
    matched_sites: output of scan_codebase.scan_codebase() filtered to is_affected sites.
    Returns each site enriched with 'original_snippet' and 'fixed_snippet'.
    """
    use_real = active_provider() != "mock"
    fixes = []

    for site in matched_sites:
        if not site["is_affected"]:
            continue
        change = site["affected_by"][0]  # primary change for this demo
        original_snippet = _get_snippet(site["file"], site["line"])

        if use_real:
            fixed_snippet = _call_llm_for_fix(
                original_snippet,
                change["migration_note"],
                change["old_pattern"],
                change["new_pattern"]
            )
        else:
            fixed_snippet = MOCK_FIXES[change["change_id"]]

        fixes.append({
            **site,
            "change_id": change["change_id"],
            "migration_note": change["migration_note"],
            "original_snippet": original_snippet,
            "fixed_snippet": fixed_snippet
        })

    return fixes


if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from modules.detect_changes import detect_changes
    from modules.scan_codebase import scan_codebase

    changes = [c["structured"] for c in detect_changes()]
    matches = scan_codebase(changes)
    fixes = generate_fixes(matches)
    print(json.dumps(fixes, indent=2))
    print(f"\nGenerated {len(fixes)} fix(es).")
