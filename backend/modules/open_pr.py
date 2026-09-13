"""
Module 4: PR Automation

REAL mode (GITHUB_TOKEN in .env, plus a repo - either GITHUB_REPO in .env
or passed in per-run from the UI):
  - Bootstraps the demo file into the target repo if it isn't there yet
    (so this works against a brand-new empty repo, not just one that
    already mirrors this project's structure).
  - Creates a uniquely-named branch (so reruns don't collide), commits the
    fix, opens an actual PR via the GitHub API.
  - Any failure is caught and returned as {"error": "..."} instead of a
    broken/partial PR object, so the UI can show a real reason instead of
    a dead link.

MOCK mode (default, or if GITHUB_TOKEN is missing): returns a realistic PR
object so the UI and demo flow are identical either way.
"""

import os
import time
import base64
import requests

GITHUB_API = "https://api.github.com"


class GitHubError(Exception):
    pass


def _check(resp: requests.Response, action: str):
    if not resp.ok:
        detail = ""
        try:
            detail = resp.json().get("message", "")
        except Exception:
            pass
        raise GitHubError(f"GitHub API error during '{action}': {resp.status_code} {detail}")
    return resp.json()


def _real_open_pr(fix: dict, repo: str) -> dict:
    token = os.environ["GITHUB_TOKEN"]
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    repo_info = _check(requests.get(f"{GITHUB_API}/repos/{repo}", headers=headers), "read repo")
    base_branch = repo_info.get("default_branch", "main")

    ref_resp = requests.get(f"{GITHUB_API}/repos/{repo}/git/ref/heads/{base_branch}", headers=headers)
    file_path = f"demo_repo/{fix['file']}"

    if ref_resp.status_code == 404:
        # Brand-new empty repo with no commits yet: bootstrap it with the
        # demo file itself, on the default branch, before branching off it.
        create_resp = requests.put(
            f"{GITHUB_API}/repos/{repo}/contents/{file_path}",
            headers=headers,
            json={
                "message": "Bootstrap: add demo checkout.py",
                "content": base64.b64encode(_local_demo_file_content().encode()).decode(),
                "branch": base_branch
            }
        )
        _check(create_resp, "bootstrap demo file into empty repo")
        ref_resp = requests.get(f"{GITHUB_API}/repos/{repo}/git/ref/heads/{base_branch}", headers=headers)

    ref_data = _check(ref_resp, "read base branch ref")
    base_sha = ref_data["object"]["sha"]

    # Unique branch name so reruns of the demo don't collide with a
    # previous run's branch (GitHub rejects creating a ref that exists).
    new_branch = f"api-change-agent/{fix['change_id']}-{int(time.time())}"
    _check(requests.post(
        f"{GITHUB_API}/repos/{repo}/git/refs",
        headers=headers,
        json={"ref": f"refs/heads/{new_branch}", "sha": base_sha}
    ), "create branch")

    file_resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/contents/{file_path}",
        headers=headers, params={"ref": new_branch}
    )
    if file_resp.status_code == 404:
        # File still doesn't exist even on the bootstrapped default branch
        # (e.g. repo had other content but not this file) - add it fresh.
        put_resp = requests.put(
            f"{GITHUB_API}/repos/{repo}/contents/{file_path}",
            headers=headers,
            json={
                "message": f"Fix: {fix['migration_note']}",
                "content": base64.b64encode(_local_demo_file_content().encode()).decode(),
                "branch": new_branch
            }
        )
        _check(put_resp, "create demo file on branch")
    else:
        file_data = _check(file_resp, "read demo file on branch")
        current_content = base64.b64decode(file_data["content"]).decode()
        updated_content = current_content.replace(fix["original_snippet"], fix["fixed_snippet"])
        if updated_content == current_content:
            raise GitHubError(
                "The original code snippet wasn't found in the target repo's file - "
                "the repo's checkout.py doesn't match what the pipeline scanned."
            )
        _check(requests.put(
            f"{GITHUB_API}/repos/{repo}/contents/{file_path}",
            headers=headers,
            json={
                "message": f"Fix: {fix['migration_note']}",
                "content": base64.b64encode(updated_content.encode()).decode(),
                "sha": file_data["sha"],
                "branch": new_branch
            }
        ), "commit fix")

    pr_data = _check(requests.post(
        f"{GITHUB_API}/repos/{repo}/pulls",
        headers=headers,
        json={
            "title": f"[API Change Agent] {fix['migration_note']}",
            "head": new_branch,
            "base": base_branch,
            "body": _pr_body(fix)
        }
    ), "open PR")

    return {
        "pr_number": pr_data.get("number"),
        "pr_url": pr_data.get("html_url"),
        "branch": new_branch,
        "title": f"[API Change Agent] {fix['migration_note']}",
        "body": _pr_body(fix)
    }


def _local_demo_file_content() -> str:
    from pathlib import Path
    return (Path(__file__).parent.parent / "demo_repo" / "checkout.py").read_text()


def _pr_body(fix: dict) -> str:
    return (
        f"## Stripe API change detected\n\n"
        f"**File:** `{fix['file']}` (line {fix['line']})\n"
        f"**SDK method:** `{fix['sdk_method']}`\n\n"
        f"**What changed:** {fix['migration_note']}\n\n"
        f"### Before\n```python\n{fix['original_snippet']}\n```\n\n"
        f"### After\n```python\n{fix['fixed_snippet']}\n```\n\n"
        f"---\n_Opened automatically by the API Change Agent pipeline._"
    )


def open_pr(fix: dict, repo_override: str | None = None) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    repo = repo_override or os.environ.get("GITHUB_REPO")
    use_real = bool(token and repo)

    if use_real:
        try:
            return _real_open_pr(fix, repo)
        except GitHubError as e:
            return {
                "error": str(e),
                "title": f"[API Change Agent] {fix['migration_note']}",
                "mock": False
            }
        except Exception as e:
            return {
                "error": f"Unexpected error opening PR: {e}",
                "title": f"[API Change Agent] {fix['migration_note']}",
                "mock": False
            }

    # MOCK: deterministic fake PR so the demo works with zero config
    return {
        "pr_number": 1000 + hash(fix["change_id"]) % 100,
        "pr_url": f"https://github.com/your-org/your-repo/pull/{1000 + hash(fix['change_id']) % 100}",
        "branch": f"api-change-agent/{fix['change_id']}",
        "title": f"[API Change Agent] {fix['migration_note']}",
        "body": _pr_body(fix),
        "mock": True
    }


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from modules.detect_changes import detect_changes
    from modules.scan_codebase import scan_codebase
    from modules.generate_fix import generate_fixes

    changes = [c["structured"] for c in detect_changes()]
    matches = scan_codebase(changes)
    fixes = generate_fixes(matches)
    prs = [open_pr(f) for f in fixes]
    print(json.dumps(prs, indent=2))
    print(f"\nOpened {len(prs)} PR(s) ({'mock' if prs and prs[0].get('mock') else 'real'} mode).")
