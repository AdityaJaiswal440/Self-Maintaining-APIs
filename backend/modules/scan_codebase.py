"""
Module 2: Codebase Impact Analysis

Approach (deliberately simple and explainable, not a black box):
  1. Static pass: regex/AST-lite scan of the demo repo for any line that
     calls a stripe.<Class>.<method>(...) pattern, recording file, line
     number, and the SDK method used.
  2. Match pass: for each call site, check whether its sdk_method matches
     any change record's sdk_method AND (for the 'source' removal case)
     whether the actual arguments used trigger that specific change.
     This second check matters: two call sites can use the same SDK method
     but only one of them uses the affected argument.

This keeps false positives low — e.g. refund_order() below uses a
different Stripe class entirely and is correctly never flagged.
"""

import ast
from pathlib import Path

DEMO_REPO_PATH = Path(__file__).parent.parent / "demo_repo"


def _extract_call_sites(file_path: Path) -> list[dict]:
    """Parse a Python file's AST and pull out every stripe.X.Y(...) call site."""
    source = file_path.read_text()
    tree = ast.parse(source)
    call_sites = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match patterns like stripe.Charge.create or stripe.PaymentIntent.confirm
        if (isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "stripe"):
            sdk_class = func.value.attr
            sdk_method_name = func.attr
            sdk_method = f"stripe.{sdk_class}.{sdk_method_name}"
            kwarg_names = [kw.arg for kw in node.keywords if kw.arg]
            call_sites.append({
                "file": file_path.name,
                "line": node.lineno,
                "sdk_method": sdk_method,
                "kwargs_used": kwarg_names,
                "source_line": source.splitlines()[node.lineno - 1].strip()
            })
    return call_sites


def scan_codebase(change_records: list[dict]) -> list[dict]:
    """
    change_records: the 'structured' objects from Module 1.
    Returns a list of matches: each call site paired with the change
    record(s) it's affected by, or an empty match list if unaffected.
    """
    py_files = list(DEMO_REPO_PATH.glob("*.py"))
    all_call_sites = []
    for f in py_files:
        all_call_sites.extend(_extract_call_sites(f))

    matches = []
    for site in all_call_sites:
        affected_by = []
        for record in change_records:
            if record["sdk_method"] != site["sdk_method"]:
                continue
            # Extra precision: the 'source' removal only affects call sites
            # that actually pass a 'source' kwarg to PaymentIntent.confirm.
            if record["change_id"] == "source-param-removed":
                if "source" in site["kwargs_used"]:
                    affected_by.append(record)
            else:
                affected_by.append(record)

        matches.append({
            **site,
            "affected_by": affected_by,
            "is_affected": len(affected_by) > 0
        })

    return matches


if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from modules.detect_changes import detect_changes

    changes = [c["structured"] for c in detect_changes()]
    results = scan_codebase(changes)
    print(json.dumps(results, indent=2))

    affected = [r for r in results if r["is_affected"]]
    unaffected = [r for r in results if not r["is_affected"]]
    print(f"\n{len(affected)} affected call site(s), {len(unaffected)} correctly ignored.")
