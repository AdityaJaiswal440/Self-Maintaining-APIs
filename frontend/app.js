const BACKEND = ""; // same origin, backend serves the frontend too

function logLine(text, cls) {
  const log = document.getElementById("log");
  const first = log.querySelector(".line");
  if (first && first.textContent.startsWith("Waiting")) first.remove();
  const div = document.createElement("div");
  div.className = "line" + (cls ? " " + cls : "");
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function setStage(n, state) {
  const node = document.querySelector(`.node[data-stage="${n}"]`);
  node.classList.remove("active", "done");
  if (state) node.classList.add(state);

  const connBefore = document.querySelector(`.connector[data-conn="${n - 1}"]`);
  const connAfter = document.querySelector(`.connector[data-conn="${n}"]`);
  if (connBefore) { connBefore.classList.remove("flowing"); connBefore.classList.add("done"); }
  if (state === "active" && connAfter) connAfter.classList.add("flowing");
  if (state === "done" && connAfter) { connAfter.classList.remove("flowing"); }
}

function tagClass(type) {
  if (type === "breaking") return "breaking";
  if (type === "deprecation") return "deprecation";
  return "feature";
}

function renderStage1(results) {
  const body = document.getElementById("stage1-body");
  body.innerHTML = "";
  results.forEach(r => {
    const s = r.structured;
    const card = document.createElement("div");
    card.className = "change-card";
    card.innerHTML = `
      <div class="change-top">
        <span class="change-title">${r.input_title}</span>
        <span class="tag ${tagClass(s.type)}">${s.type}${s.requires_action ? "" : " · no action needed"}</span>
      </div>
      <div class="change-note">${s.migration_note}</div>
      <div class="change-method">${s.sdk_method} → severity: ${s.severity}</div>
    `;
    body.appendChild(card);
  });
}

function diffLines(original, fixed) {
  // Simple line-level diff for display purposes: show removed lines then added lines.
  const origLines = original.split("\n");
  const fixedLines = fixed.split("\n");
  let html = "";
  origLines.forEach(l => { if (l.trim()) html += `<span class="removed">- ${escapeHtml(l)}</span>`; });
  fixedLines.forEach(l => { if (l.trim()) html += `<span class="added">+ ${escapeHtml(l)}</span>`; });
  return html;
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderStage3(results) {
  const body = document.getElementById("stage3-body");
  body.innerHTML = "";
  results.forEach(r => {
    const card = document.createElement("div");
    card.className = "diff-card";
    card.innerHTML = `
      <div class="diff-head">
        <div>${r.migration_note}</div>
        <div class="loc">${r.file}:${r.line} · ${r.sdk_method}</div>
      </div>
      <pre class="diff">${diffLines(r.original_snippet, r.fixed_snippet)}</pre>
    `;
    body.appendChild(card);
  });
}

function renderStage4(results) {
  const body = document.getElementById("stage4-body");
  body.innerHTML = "";
  results.forEach(r => {
    const card = document.createElement("div");
    if (r.error) {
      card.className = "pr-card";
      card.style.borderColor = "var(--accent-red)";
      card.innerHTML = `
        <div>
          <div class="pr-title" style="color: var(--accent-red);">Failed to open PR</div>
          <div class="pr-meta">${escapeHtml(r.error)}</div>
        </div>
      `;
    } else {
      card.className = "pr-card";
      card.innerHTML = `
        <div>
          <div class="pr-title">${r.title}</div>
          <div class="pr-meta">branch: ${r.branch} ${r.mock ? "· mock PR (no GitHub repo/token configured)" : ""}</div>
        </div>
        <a class="pr-link" href="${r.pr_url}" target="_blank" rel="noopener">View PR →</a>
      `;
    }
    body.appendChild(card);
  });
}

function renderSummary(summary) {
  const body = document.getElementById("summary-body");
  const items = [
    ["changes_detected", "Changes parsed"],
    ["call_sites_scanned", "Call sites scanned"],
    ["call_sites_affected", "Call sites affected"],
    ["fixes_generated", "Fixes generated"],
    ["prs_opened", "PRs opened"]
  ];
  body.innerHTML = `<div class="summary-bar">` + items.map(([key, label]) => `
    <div class="summary-item">
      <div class="summary-num">${summary[key]}</div>
      <div class="summary-label">${label}</div>
    </div>
  `).join("") + `</div>`;
}

function runPipeline() {
  const btn = document.getElementById("run-btn");
  btn.disabled = true;
  btn.textContent = "Running…";

  document.getElementById("log").innerHTML = "";
  [1, 2, 3, 4].forEach(n => setStage(n, null));
  document.querySelectorAll(".connector").forEach(c => c.classList.remove("done", "flowing"));

  setStage(1, "active");
  logLine("Starting pipeline run against demo_repo/checkout.py...");

  const repo = document.getElementById("repo-input").value.trim();
  const url = repo ? `${BACKEND}/run?repo=${encodeURIComponent(repo)}` : `${BACKEND}/run`;
  const source = new EventSource(url);

  source.addEventListener("stage1_complete", e => {
    const data = JSON.parse(e.data);
    logLine(`Stage 1 done — parsed ${data.results.length} changelog entr${data.results.length === 1 ? "y" : "ies"}.`, "ok");
    renderStage1(data.results);
    setStage(1, "done");
    setStage(2, "active");
  });

  source.addEventListener("stage2_complete", e => {
    const data = JSON.parse(e.data);
    const affected = data.results.filter(r => r.is_affected).length;
    const ignored = data.results.length - affected;
    logLine(`Stage 2 done — ${affected} call site(s) affected, ${ignored} correctly ignored.`, "ok");
    setStage(2, "done");
    setStage(3, "active");
  });

  source.addEventListener("stage3_complete", e => {
    const data = JSON.parse(e.data);
    logLine(`Stage 3 done — generated ${data.results.length} fix(es).`, "ok");
    renderStage3(data.results);
    setStage(3, "done");
    setStage(4, "active");
  });

  source.addEventListener("stage4_error", e => {
    const data = JSON.parse(e.data);
    logLine(`Stage 4 error: ${data.error}`, "warn");
  });

  source.addEventListener("stage4_complete", e => {
    const data = JSON.parse(e.data);
    const mock = data.results.some(r => r.mock);
    logLine(`Stage 4 done — opened ${data.results.length} PR(s).${mock ? " (mock mode — set GITHUB_TOKEN/GITHUB_REPO for real PRs)" : ""}`, mock ? "warn" : "ok");
    renderStage4(data.results);
    setStage(4, "done");
  });

  source.addEventListener("pipeline_complete", e => {
    const data = JSON.parse(e.data);
    logLine("Pipeline complete.", "ok");
    renderSummary(data.summary);
    document.getElementById("mode-tag").textContent = "mode: " +
      (data.summary.prs_opened && document.querySelector(".pr-meta")?.textContent.includes("mock") ? "mock (no API keys set)" : "live");
    btn.disabled = false;
    btn.textContent = "Run again";
    source.close();
  });

  source.onerror = () => {
    logLine("Connection error — is the backend running on the expected port?", "warn");
    btn.disabled = false;
    btn.textContent = "Run pipeline";
    source.close();
  };
}
