"""
FastAPI backend for the API Change Agent demo.

Exposes a single streaming endpoint, /run, that executes the full
4-stage pipeline and pushes a Server-Sent Event after each stage
completes, so the frontend can animate stage-by-stage instead of
waiting for one big response.
"""

import json
from pathlib import Path

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from modules.detect_changes import detect_changes
from modules.scan_codebase import scan_codebase
from modules.generate_fix import generate_fixes
from modules.open_pr import open_pr

app = FastAPI(title="API Change Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _pipeline_stream(repo_override: str | None):
    # Stage 1
    changes_raw = detect_changes()
    changes = [c["structured"] for c in changes_raw]
    yield _sse("stage1_complete", {"results": changes_raw})

    # Stage 2
    matches = scan_codebase(changes)
    yield _sse("stage2_complete", {"results": matches})

    # Stage 3
    affected = [m for m in matches if m["is_affected"]]
    fixes = generate_fixes(affected)
    yield _sse("stage3_complete", {"results": fixes})

    # Stage 4
    prs = []
    for f in fixes:
        pr = open_pr(f, repo_override=repo_override)
        prs.append(pr)
        if pr.get("error"):
            yield _sse("stage4_error", {"error": pr["error"]})
    yield _sse("stage4_complete", {"results": prs})

    yield _sse("pipeline_complete", {"summary": {
        "changes_detected": len(changes),
        "call_sites_scanned": len(matches),
        "call_sites_affected": len(affected),
        "fixes_generated": len(fixes),
        "prs_opened": len(prs)
    }})


@app.get("/run")
def run_pipeline(repo: str | None = None):
    """
    repo: optional 'owner/name' GitHub repo, passed from the UI's input
    field. Overrides GITHUB_REPO from .env for this run only. GITHUB_TOKEN
    always comes from .env, never from the browser, for safety.
    """
    return StreamingResponse(_pipeline_stream(repo), media_type="text/event-stream")


@app.get("/api/demo-repo")
def get_demo_repo():
    """Lets the UI display the 'victim' codebase before the run starts."""
    demo_file = Path(__file__).parent / "demo_repo" / "checkout.py"
    return {"filename": "checkout.py", "content": demo_file.read_text()}


# Serve the frontend
app.mount("/", StaticFiles(directory=str(Path(__file__).parent.parent / "frontend"), html=True), name="frontend")
