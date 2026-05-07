const DEFAULT_API_BASE = "http://127.0.0.1:8000";

function resolveApiBase() {
  const params = new URLSearchParams(window.location.search);
  const override = params.get("api") || window.localStorage.getItem("bharatProcureApiBase");
  if (override) {
    return override.replace(/\/$/, "");
  }

  if (window.location.protocol === "file:") {
    return DEFAULT_API_BASE;
  }

  const isFastApiUi = window.location.pathname.startsWith("/ui/");
  const isBackendPort = window.location.port === "8000";
  if (isFastApiUi || isBackendPort) {
    return window.location.origin;
  }

  const isLocalStaticServer = ["localhost", "127.0.0.1", ""].includes(window.location.hostname);
  return isLocalStaticServer ? DEFAULT_API_BASE : window.location.origin;
}

const API_BASE = resolveApiBase();
const PAGE_ID = document.body.dataset.page || "dashboard";

const appState = {
  metrics: null,
  officer: null,
  latest: null,
  history: [],
  recentAudit: [],
  fullAudit: [],
  upload: {
    tenderFile: null,
    bidderFiles: [],
    running: false,
    selectedDocIndex: 0,
    lastResult: null,
  },
};

const dom = {
  pageRoot: document.getElementById("pageRoot"),
  activeTenderLabel: document.getElementById("activeTenderLabel"),
  officerName: document.getElementById("officerName"),
  officerMeta: document.getElementById("officerMeta"),
  officerAvatar: document.getElementById("officerAvatar"),
  notifCount: document.getElementById("notifCount"),
  searchInput: document.getElementById("globalSearch"),
  statActiveTenders: document.getElementById("statActiveTenders"),
  statBiddersToday: document.getElementById("statBiddersToday"),
  statHitlPending: document.getElementById("statHitlPending"),
  statLatestScore: document.getElementById("statLatestScore"),
  statAuditEntries: document.getElementById("statAuditEntries"),
  navBidderCount: document.getElementById("navBidderCount"),
  navEvalCount: document.getElementById("navEvalCount"),
  navLinks: [...document.querySelectorAll(".nav-item")],
  notificationButton: document.querySelector(".icon-button"),
  brandMark: document.querySelector(".brand-mark"),
};

document.addEventListener("DOMContentLoaded", initApp);

async function initApp() {
  setActiveNav();
  bindGlobalSearch();
  bindHeaderActions();
  await hydrateState();
  renderGlobalChrome();
  renderPage();
  lucide.createIcons();
}

function setActiveNav() {
  dom.navLinks.forEach((link) => {
    if (link.dataset.page === PAGE_ID) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });
}

function bindGlobalSearch() {
  dom.searchInput.addEventListener("input", () => {
    applySearchFilter(dom.searchInput.value.trim().toLowerCase());
  });
}

function bindOfficerCard() {
  const officerCard = document.getElementById("officerCard");
  officerCard?.addEventListener("click", () => {
    if (!appState.officer) return;
    const details = [
      appState.officer.name,
      appState.officer.role,
      appState.officer.department,
    ].filter(Boolean).join(" | ");
    showToast(details);
    return;
    showToast(`${appState.officer.name} · ${appState.officer.role} · ${appState.officer.department}`);
  });
}

function bindHeaderActions() {
  dom.brandMark?.addEventListener("click", () => {
    window.location.href = "./dashboard_v1.html";
  });

  dom.notificationButton?.addEventListener("click", () => {
    window.location.href = "./audit_trail.html";
  });

  const officerCard = document.getElementById("officerCard");
  officerCard?.addEventListener("click", () => {
    if (PAGE_ID !== "settings") {
      window.location.href = "./settings.html";
      return;
    }
    if (!appState.officer) return;
    const details = [
      appState.officer.name,
      appState.officer.role,
      appState.officer.department,
    ].filter(Boolean).join(" | ");
    showToast(details);
    return;
    showToast(`${appState.officer.name} · ${appState.officer.role} · ${appState.officer.department}`);
  });
}

function sanitizeRenderedText() {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const replacements = [
    ["Â·", "·"],
    ["â†’", "->"],
    ["â€¦", "..."],
  ];

  replacements.push(
    ["\u00C2\u00B7", " | "],
    ["\u00E2\u2020\u2019", " -> "],
    ["\u00E2\u20AC\u00A6", "..."],
  );

  let node = walker.nextNode();
  while (node) {
    let value = node.nodeValue;
    replacements.forEach(([search, replace]) => {
      value = value.replaceAll(search, replace);
    });
    if (value !== node.nodeValue) {
      node.nodeValue = value;
    }
    node = walker.nextNode();
  }
}

async function hydrateState() {
  try {
    const dashboardState = await fetchJson("/dashboard-state");
    appState.metrics = dashboardState.metrics || {};
    appState.officer = dashboardState.officer_profile || null;
    appState.latest = dashboardState.latest_evaluation?.pipeline_results || null;
    appState.history = dashboardState.evaluation_history || [];
    appState.recentAudit = dashboardState.recent_audit || [];
    if (PAGE_ID === "audit") {
      const auditState = await fetchJson("/audit-trail");
      appState.fullAudit = [...(auditState.entries || [])].reverse();
    }
  } catch (error) {
    appState.metrics = {
      active_tenders: 0,
      bidders_evaluated_today: 0,
      hitl_pending: 0,
      latest_score_percent: null,
      audit_entries: 0,
    };
    appState.officer = {
      name: "Backend Offline",
      role: "Start FastAPI Server",
      department: API_BASE,
      clearance_level: "N/A",
      officer_id: "OFFLINE",
    };
    appState.latest = null;
    appState.history = [];
    appState.recentAudit = [];
    appState.fullAudit = [];
  }
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : { error: await response.text() };
  if (!response.ok || data.error) {
    throw new Error(data.error || `Request failed for ${path}`);
  }
  return data;
}

function renderGlobalChrome() {
  const officer = appState.officer || {};
  const metrics = appState.metrics || {};
  const latest = appState.latest;

  dom.activeTenderLabel.textContent = latest?.tender_id
    ? `Active: ${latest.tender_id}`
    : "Active: Awaiting upload";
  dom.officerName.textContent = officer.name || "Officer";
  dom.officerMeta.textContent = `${officer.role || "Officer"} · ${officer.department || "Local"} · ${officer.clearance_level || "L1"}`;
  dom.officerAvatar.textContent = getInitials(officer.name || "Officer");
  dom.officerMeta.textContent = [
    officer.role || "Officer",
    officer.department || "Local",
    officer.clearance_level || "L1",
  ].join(" | ");
  dom.notifCount.textContent = metrics.hitl_pending ?? 0;
  dom.statActiveTenders.textContent = metrics.active_tenders ?? 0;
  dom.statBiddersToday.textContent = metrics.bidders_evaluated_today ?? 0;
  dom.statHitlPending.textContent = metrics.hitl_pending ?? 0;
  dom.statLatestScore.textContent = metrics.latest_score_percent != null ? `${metrics.latest_score_percent}%` : "--";
  dom.statAuditEntries.textContent = metrics.audit_entries ?? 0;
  if (dom.navBidderCount) dom.navBidderCount.textContent = String(appState.history.length);
  if (dom.navEvalCount) dom.navEvalCount.textContent = String(appState.history.filter((item) => (item.open_review_count || 0) > 0).length);
  sanitizeRenderedText();
}

function renderPage() {
  if (PAGE_ID === "dashboard") {
    renderDashboardPage();
  } else if (PAGE_ID === "upload") {
    renderUploadPage();
  } else if (PAGE_ID === "bidders") {
    renderBiddersPage();
  } else if (PAGE_ID === "active-evals") {
    renderActiveEvalsPage();
  } else if (PAGE_ID === "analytics") {
    renderAnalyticsPage();
  } else if (PAGE_ID === "audit") {
    renderAuditPage();
  } else if (PAGE_ID === "settings") {
    renderSettingsPage();
  } else if (PAGE_ID === "help") {
    renderHelpPage();
  }
  applySearchFilter(dom.searchInput.value.trim().toLowerCase());
  sanitizeRenderedText();
  lucide.createIcons();
}

function renderDashboardPage() {
  const latest = appState.latest;
  const latestDoc = latest?.extracted_documents?.[0] || null;
  const latestVerdict = latest?.final_verdict || {};
  const historyCards = appState.history.slice(0, 3);

  dom.pageRoot.innerHTML = `
    <section class="page-header">
      <h1>Dashboard</h1>
      <p>Live summary of the latest bidder evaluation, actual extracted text, and recent audit updates.</p>
    </section>

    <section class="grid-2">
        <article class="page-card searchable" data-search-text="${escapeHtml(searchBlob(getDisplayBidderName(latest), latest?.tender_id, latestVerdict.summary))}">
        <div class="section-header">
          <div>
            <div class="section-title">Latest Evaluation</div>
            <div class="section-subtitle">${escapeHtml(latest?.tender_checklist?.tender_title || "No live evaluation yet")}</div>
          </div>
          ${latest ? renderVerdictTag(latestVerdict.bidder_verdict) : ""}
        </div>
        ${latest ? `
          <div class="score-block">
            <div class="score-number">${escapeHtml(String(latestVerdict.score_percent ?? "--"))}</div>
            <div class="score-label">% live score</div>
          </div>
          <p style="margin-top:12px">${escapeHtml(latestVerdict.summary || "No summary available.")}</p>
          <div class="pill-row" style="margin-top:16px">
            <span class="tag info">${escapeHtml(getDisplayBidderName(latest))}</span>
            <span class="tag ${latestVerdict.human_review_items?.length ? "warning" : "success"}">${escapeHtml(`${latestVerdict.human_review_items?.length || 0} review item(s)`)}</span>
          </div>
        ` : `<div class="notice">Run an evaluation on the Upload Tender page to populate live dashboard data.</div>`}
      </article>

      <article class="page-card searchable" data-search-text="${escapeHtml(searchBlob(latestDoc?.document_type, latestDoc?.entity_name, latestDoc?.source_text_excerpt))}">
        <div class="section-header">
          <div>
            <div class="section-title">AI Extracted Text</div>
            <div class="section-subtitle">${escapeHtml(latestDoc?.source_filename || "Waiting for uploaded document")}</div>
          </div>
          ${latestDoc ? renderConfidenceTag(latestDoc.confidence_score) : ""}
        </div>
        <div class="document-preview">${escapeHtml(latestDoc?.source_text_excerpt || "Upload bidder files to see text extracted from the actual document.")}</div>
      </article>
    </section>

    <section class="grid-2">
      <article class="panel">
        <div class="section-header">
          <div>
            <div class="section-title">Recent Evaluations</div>
            <div class="section-subtitle">Latest bidder decisions captured from real runs.</div>
          </div>
        </div>
        ${historyCards.length ? `
          <div class="grid-3">
            ${historyCards.map((item) => `
              <div class="page-card searchable" data-search-text="${escapeHtml(searchBlob(getDisplayBidderName(item), item.tender_id, item.summary))}">
                <h3>${escapeHtml(getDisplayBidderName(item))}</h3>
                <p>${escapeHtml(item.summary || "No summary available.")}</p>
                <div class="pill-row" style="margin-top:14px">
                  ${renderVerdictTag(item.verdict)}
                  <span class="tag info">${escapeHtml(item.tender_id || "UNKNOWN")}</span>
                </div>
              </div>
            `).join("")}
          </div>
        ` : `<div class="notice">No completed evaluations yet.</div>`}
      </article>

      <article class="panel">
        <div class="section-header">
          <div>
            <div class="section-title">Recent Audit Activity</div>
            <div class="section-subtitle">Most recent persisted audit entries.</div>
          </div>
        </div>
        ${renderAuditList(appState.recentAudit.slice(0, 6))}
      </article>
    </section>
  `;
}

function renderUploadPage() {
  const activeResult = appState.upload.lastResult || appState.latest;
  const documents = activeResult?.extracted_documents || [];
  const selectedDoc = documents[appState.upload.selectedDocIndex] || documents[0] || null;
  const criteria = buildCriteria(activeResult);
  const verdict = activeResult?.final_verdict || {};

  dom.pageRoot.innerHTML = `
    <section class="page-header">
      <h1>Upload Tender</h1>
      <p>Upload one tender PDF and the bidder submission files, then run the live pipeline. The extracted text below comes directly from the uploaded files.</p>
    </section>

    <section class="panel">
      <div class="section-header">
        <div>
          <div class="section-title">Live Intake</div>
          <div class="section-subtitle">Tender PDF plus bidder documents</div>
        </div>
        ${activeResult ? renderVerdictTag(verdict.bidder_verdict) : ""}
      </div>
      <div class="upload-box" id="uploadDropZone">
        <div class="helper-text">Drop files here or use the file pickers below. PDFs and images are supported.</div>
        <div class="upload-grid">
          <div class="upload-tile">
            <label for="uploadTenderFile">Tender PDF</label>
            <input id="uploadTenderFile" type="file" accept=".pdf">
            <div class="muted" id="uploadTenderName">${escapeHtml(appState.upload.tenderFile?.name || "No tender file selected")}</div>
          </div>
          <div class="upload-tile">
            <label for="uploadBidderFiles">Bidder Submissions</label>
            <input id="uploadBidderFiles" type="file" accept=".pdf,.png,.jpg,.jpeg" multiple>
            <div class="muted" id="uploadBidderName">${escapeHtml(appState.upload.bidderFiles.length ? `${appState.upload.bidderFiles.length} file(s) selected` : "No bidder files selected")}</div>
          </div>
        </div>
        <div class="button-row" style="margin-top:16px">
          <button class="btn btn-primary" id="runPipelineBtn" ${appState.upload.running ? "disabled" : ""}>${appState.upload.running ? "Running..." : "Run Live Evaluation"}</button>
          <button class="btn btn-secondary" id="clearUploadBtn">Clear Selection</button>
          ${activeResult?.saved_tender?.saved_url ? `<a class="btn btn-secondary" href="${escapeHtml(resolveApiResource(activeResult.saved_tender.saved_url))}" target="_blank" rel="noreferrer">Open Saved Tender</a>` : ""}
        </div>
        <div class="helper-text" id="uploadStatusText" style="margin-top:14px">${escapeHtml(getUploadStatusText())}</div>
        ${activeResult?.upload_run_id ? `<div class="helper-text" style="margin-top:8px">Saved run: ${escapeHtml(activeResult.upload_run_id)}</div>` : ""}
      </div>
    </section>

    <section class="grid-2">
      <article class="panel">
        <div class="section-header">
          <div>
            <div class="section-title">Uploaded Document Text</div>
            <div class="section-subtitle">${escapeHtml(selectedDoc?.source_filename || "Select files and run the pipeline")}</div>
          </div>
          ${selectedDoc ? renderConfidenceTag(selectedDoc.confidence_score) : ""}
        </div>
        <div class="doc-list">
          ${documents.length ? documents.map((document, index) => `
            <button class="doc-item ${index === appState.upload.selectedDocIndex ? "active" : ""} searchable" data-doc-index="${index}" data-search-text="${escapeHtml(searchBlob(document.document_type, document.entity_name, document.source_text_excerpt))}" style="text-align:left">
              <div class="doc-title">${escapeHtml(document.document_type || document.source_filename || "Uploaded document")}</div>
              <div class="doc-meta">${escapeHtml(document.entity_name || "Entity not extracted")} · ${escapeHtml(document.source_filename || "No filename")}</div>
            </button>
          `).join("") : `<div class="notice">No uploaded results yet. After a run, each uploaded file will appear here with its extracted text.</div>`}
        </div>
        ${selectedDoc?.saved_url ? `
          <div class="button-row" style="margin-top:16px">
            <a class="btn btn-secondary" href="${escapeHtml(resolveApiResource(selectedDoc.saved_url))}" target="_blank" rel="noreferrer">Open Saved File</a>
            <span class="tag success">${escapeHtml(formatFileSize(selectedDoc.saved_size_bytes))} saved</span>
          </div>
        ` : ""}
        <div class="document-preview" style="margin-top:16px">${escapeHtml(selectedDoc?.source_text_excerpt || "AI extracted text will appear here after evaluation.")}</div>
      </article>

      <article class="panel">
        <div class="section-header">
          <div>
            <div class="section-title">Criteria & Officer Actions</div>
            <div class="section-subtitle">${escapeHtml(activeResult ? getDisplayBidderName(activeResult) : "No bidder loaded")}</div>
          </div>
        </div>
        ${criteria.length ? `
          <div class="criteria-list">
            ${criteria.map((criterion) => `
              <div class="criteria-item searchable" data-search-text="${escapeHtml(searchBlob(criterion.criterion, criterion.note, criterion.evidence))}">
                <div class="criteria-title">${escapeHtml(criterion.criterion)}</div>
                <div class="criteria-meta">${escapeHtml(criterion.note || "No note available")}</div>
                <div class="pill-row" style="margin-top:10px">
                  ${renderVerdictTag(criterion.status)}
                  <span class="tag info">${escapeHtml(`Evidence: ${truncate(criterion.evidence || "N/A", 32)}`)}</span>
                </div>
              </div>
            `).join("")}
          </div>
          <div class="field-block" style="margin-top:16px">
            <label for="officerNoteInput">Officer Notes</label>
            <textarea id="officerNoteInput" placeholder="Add your verification note here...">${escapeHtml(appState.upload.officerNote || "")}</textarea>
          </div>
          <div class="button-row" style="margin-top:16px">
            <button class="btn btn-success" data-officer-action="MANUAL_ACCEPT_EVIDENCE">Accept Evidence</button>
            <button class="btn btn-danger" data-officer-action="MANUAL_REJECT_EVIDENCE">Reject Evidence</button>
            <button class="btn btn-warning" data-officer-action="REQUEST_ORIGINAL_DOCUMENT">Request Original</button>
          </div>
        ` : `<div class="notice">Criteria results will appear here after the live pipeline finishes.</div>`}
      </article>
    </section>
  `;

  bindUploadPageEvents();
}

function bindUploadPageEvents() {
  const tenderInput = document.getElementById("uploadTenderFile");
  const bidderInput = document.getElementById("uploadBidderFiles");
  const runButton = document.getElementById("runPipelineBtn");
  const clearButton = document.getElementById("clearUploadBtn");
  const officerNote = document.getElementById("officerNoteInput");
  const dropZone = document.getElementById("uploadDropZone");

  tenderInput?.addEventListener("change", (event) => {
    appState.upload.tenderFile = event.target.files[0] || null;
    renderPage();
  });

  bidderInput?.addEventListener("change", (event) => {
    appState.upload.bidderFiles = [...event.target.files];
    renderPage();
  });

  runButton?.addEventListener("click", runUploadPipeline);
  clearButton?.addEventListener("click", () => {
    appState.upload.tenderFile = null;
    appState.upload.bidderFiles = [];
    appState.upload.lastResult = null;
    appState.upload.selectedDocIndex = 0;
    renderPage();
  });

  officerNote?.addEventListener("input", (event) => {
    appState.upload.officerNote = event.target.value;
  });

  dropZone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.style.borderColor = "rgba(30,136,229,0.8)";
  });

  dropZone?.addEventListener("dragleave", () => {
    dropZone.style.borderColor = "";
  });

  dropZone?.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.style.borderColor = "";
    const files = [...event.dataTransfer.files];
    const tenderPdf = files.find((file) => file.name.toLowerCase().endsWith(".pdf"));
    const bidderDocs = files.filter((file) => file !== tenderPdf);
    if (tenderPdf) {
      appState.upload.tenderFile = tenderPdf;
    }
    if (bidderDocs.length) {
      appState.upload.bidderFiles = bidderDocs;
    }
    renderPage();
  });

  document.querySelectorAll("[data-doc-index]").forEach((button) => {
    button.addEventListener("click", () => {
      appState.upload.selectedDocIndex = Number(button.dataset.docIndex);
      renderPage();
    });
  });

  document.querySelectorAll("[data-officer-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      await logOfficerAction(button.dataset.officerAction);
    });
  });
}

async function runUploadPipeline() {
  if (appState.upload.running) return;
  if (!appState.upload.tenderFile || !appState.upload.bidderFiles.length) {
    showToast("Select the tender PDF and at least one bidder file first.");
    return;
  }

  appState.upload.running = true;
  renderPage();

  const payload = new FormData();
  payload.append("tender_pdf", appState.upload.tenderFile);
  appState.upload.bidderFiles.forEach((file) => payload.append("bidder_docs", file));
  payload.append("doc_types", appState.upload.bidderFiles.map(inferDocType).join(","));

  try {
    const response = await fetchJson("/evaluate-full-pipeline", {
      method: "POST",
      body: payload,
    });
    appState.upload.lastResult = response.pipeline_results;
    appState.upload.selectedDocIndex = 0;
    await hydrateState();
    renderGlobalChrome();
    renderPage();
    showToast("Live evaluation completed and documents saved.");
  } catch (error) {
    showToast(error.message || "The live evaluation failed.");
  } finally {
    appState.upload.running = false;
    renderPage();
  }
}

function renderBiddersPage() {
  dom.pageRoot.innerHTML = `
    <section class="page-header">
      <h1>All Bidders</h1>
      <p>Add bidder information, attach submitted documents for review, and track every recorded bidder decision.</p>
    </section>

    <section class="panel">
      <div class="section-header">
        <div>
          <div class="section-title">Add Bidder Information</div>
          <div class="section-subtitle">Saved to bidder history with review document links.</div>
        </div>
      </div>
      <form id="manualBidderForm" enctype="multipart/form-data">
        <div class="field-grid">
          <div class="field-block">
            <label for="manualBidderName">Bidder Name</label>
            <input id="manualBidderName" name="bidder_name" placeholder="ABC Infra Pvt Ltd" required>
          </div>
          <div class="field-block">
            <label for="manualTenderId">Tender Taken</label>
            <input id="manualTenderId" name="tender_id" placeholder="Tender ID or tender name" required>
          </div>
          <div class="field-block">
            <label for="manualVerdict">Verdict</label>
            <select id="manualVerdict" name="verdict">
              <option value="REFER_TO_COMMITTEE">Review</option>
              <option value="PASS">Pass</option>
              <option value="FAIL">Fail</option>
            </select>
          </div>
          <div class="field-block">
            <label for="manualBidAmount">Amount</label>
            <input id="manualBidAmount" name="bid_amount" inputmode="decimal" placeholder="1250000">
          </div>
          <div class="field-block" style="grid-column:1 / -1">
            <label for="manualBidderDocs">Uploaded Documents For Review</label>
            <input id="manualBidderDocs" name="documents" type="file" accept=".pdf,.png,.jpg,.jpeg" multiple>
          </div>
        </div>
        <div class="button-row" style="margin-top:18px">
          <button class="btn btn-primary" type="submit">Save Bidder</button>
          <button class="btn btn-secondary" type="reset">Clear Form</button>
        </div>
      </form>
    </section>

    <section class="panel">
      <div class="section-header">
        <div>
          <div class="section-title">Bidder Evaluation History</div>
          <div class="section-subtitle">${escapeHtml(`${appState.history.length} recorded evaluation(s)`)}</div>
        </div>
      </div>
      ${appState.history.length ? `
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Bidder</th>
                <th>Tender</th>
                <th>Verdict</th>
                <th>Amount</th>
                <th>Documents</th>
                <th>Review</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              ${appState.history.map((item) => `
                <tr class="searchable" data-search-text="${escapeHtml(searchBlob(getDisplayBidderName(item), item.tender_id, item.summary, item.verdict, item.bid_amount, getDocumentSearchText(item)))}">
                  <td>${escapeHtml(getDisplayBidderName(item))}</td>
                  <td>${escapeHtml(item.tender_id || "UNKNOWN")}</td>
                  <td>${renderVerdictTag(item.verdict)}</td>
                  <td>${escapeHtml(formatBidAmount(item.bid_amount))}</td>
                  <td>${renderRecordDocuments(item)}</td>
                  <td>${escapeHtml(`${item.open_review_count || 0} item(s)`)}</td>
                  <td>${escapeHtml(formatDateTime(item.generated_at))}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      ` : `<div class="notice">No bidder evaluations have been recorded yet.</div>`}
    </section>
  `;

  bindManualBidderForm();
}

function bindManualBidderForm() {
  const form = document.getElementById("manualBidderForm");
  form?.addEventListener("submit", saveManualBidder);
}

async function saveManualBidder(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  submitButton.textContent = "Saving...";

  try {
    await fetchJson("/manual-bidders", {
      method: "POST",
      body: new FormData(form),
    });
    form.reset();
    await hydrateState();
    renderGlobalChrome();
    renderPage();
    showToast("Bidder information saved.");
  } catch (error) {
    showToast(error.message || "Could not save bidder information.");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Save Bidder";
  }
}

function renderActiveEvalsPage() {
  const flagged = appState.history.filter((item) => (item.open_review_count || 0) > 0);
  dom.pageRoot.innerHTML = `
    <section class="page-header">
      <h1>Active Evals</h1>
      <p>Evaluations that still need officer attention or have open human review items.</p>
    </section>
    <section class="grid-2">
      ${(flagged.length ? flagged : appState.history.slice(0, 2)).map((item) => `
        <article class="page-card searchable" data-search-text="${escapeHtml(searchBlob(getDisplayBidderName(item), item.tender_id, item.summary, item.open_review_items?.join(" ")))}">
          <div class="section-header">
            <div>
              <div class="section-title">${escapeHtml(getDisplayBidderName(item))}</div>
              <div class="section-subtitle">${escapeHtml(item.tender_id || "UNKNOWN")}</div>
            </div>
            ${renderVerdictTag(item.verdict)}
          </div>
          <p>${escapeHtml(item.summary || "No summary available.")}</p>
          <div class="pill-row" style="margin-top:14px">
            <span class="tag warning">${escapeHtml(`${item.open_review_count || 0} review item(s)`)}</span>
            <span class="tag info">${escapeHtml(item.score_percent != null ? `${item.score_percent}% score` : "No score")}</span>
          </div>
          ${(item.open_review_items || []).length ? `
            <div class="help-list" style="margin-top:14px">
              ${(item.open_review_items || []).slice(0, 3).map((reviewItem) => `
                <div class="list-item">${escapeHtml(reviewItem)}</div>
              `).join("")}
            </div>
          ` : ""}
        </article>
      `).join("") || `<div class="notice">No active evaluations yet.</div>`}
    </section>
  `;
}

function renderAnalyticsPage() {
  const verdictBreakdown = {
    PASS: appState.history.filter((item) => item.verdict === "PASS").length,
    FAIL: appState.history.filter((item) => item.verdict === "FAIL").length,
    REFER_TO_COMMITTEE: appState.history.filter((item) => item.verdict === "REFER_TO_COMMITTEE").length,
  };
  const total = Math.max(appState.history.length, 1);
  const avgScore = appState.history.length
    ? Math.round(appState.history.reduce((sum, item) => sum + (item.score_percent || 0), 0) / appState.history.length)
    : 0;

  dom.pageRoot.innerHTML = `
    <section class="page-header">
      <h1>Analytics</h1>
      <p>Real metrics computed from the evaluations your backend has recorded so far.</p>
    </section>

    <section class="grid-3">
      <article class="page-card">
        <div class="section-title">Average Score</div>
        <div class="score-block" style="margin-top:12px">
          <div class="score-number">${avgScore}</div>
          <div class="score-label">% across recorded evaluations</div>
        </div>
      </article>
      <article class="page-card">
        <div class="section-title">Pass Rate</div>
        <div class="score-block" style="margin-top:12px">
          <div class="score-number">${Math.round((verdictBreakdown.PASS / total) * 100)}</div>
          <div class="score-label">% of all evaluations</div>
        </div>
      </article>
      <article class="page-card">
        <div class="section-title">Open Review Load</div>
        <div class="score-block" style="margin-top:12px">
          <div class="score-number">${appState.metrics?.hitl_pending ?? 0}</div>
          <div class="score-label">items pending manual review</div>
        </div>
      </article>
    </section>

    <section class="grid-2">
      <article class="panel">
        <div class="section-header">
          <div class="section-title">Verdict Breakdown</div>
        </div>
        ${renderProgressRow("Pass", verdictBreakdown.PASS, total, "success")}
        ${renderProgressRow("Fail", verdictBreakdown.FAIL, total, "danger")}
        ${renderProgressRow("Refer / Review", verdictBreakdown.REFER_TO_COMMITTEE, total, "warning")}
      </article>
      <article class="panel">
        <div class="section-header">
          <div class="section-title">Document Types Seen</div>
        </div>
        ${renderDocumentTypeStats()}
      </article>
    </section>
  `;
}

function renderDocumentTypeStats() {
  const counts = {};
  appState.history.forEach((item) => {
    (item.document_types || []).forEach((type) => {
      counts[type] = (counts[type] || 0) + 1;
    });
  });
  const entries = Object.entries(counts);
  if (!entries.length) {
    return `<div class="notice">No document type statistics yet.</div>`;
  }
  return `
    <div class="help-list">
      ${entries.map(([type, count]) => `
        <div class="list-item searchable" data-search-text="${escapeHtml(type)}">
          <strong>${escapeHtml(type)}</strong><br>
          <span class="muted">${escapeHtml(`${count} occurrence(s) in recorded evaluations`)}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function renderAuditPage() {
  dom.pageRoot.innerHTML = `
    <section class="page-header">
      <h1>Audit Trail</h1>
      <p>Full persisted audit entries from the backend. No placeholder events are shown here.</p>
    </section>
    <section class="panel">
      <div class="section-header">
        <div>
          <div class="section-title">Persistent Audit Entries</div>
          <div class="section-subtitle">${escapeHtml(`${appState.fullAudit.length} entry(s) loaded`)}</div>
        </div>
      </div>
      ${appState.fullAudit.length ? renderAuditList(appState.fullAudit) : `<div class="notice">No audit entries are available.</div>`}
    </section>
  `;
}

function renderSettingsPage() {
  const officer = appState.officer || {};
  dom.pageRoot.innerHTML = `
    <section class="page-header">
      <h1>Settings</h1>
      <p>Update the live officer profile used across the dashboard and audit actions.</p>
    </section>

    <section class="panel">
      <div class="section-header">
        <div>
          <div class="section-title">Officer Profile</div>
          <div class="section-subtitle">Saved to the backend so every page uses the same live values.</div>
        </div>
      </div>
      <form id="officerProfileForm">
        <div class="field-grid">
          <div class="field-block">
            <label for="officerIdField">Officer ID</label>
            <input id="officerIdField" name="officer_id" value="${escapeHtml(officer.officer_id || "")}">
          </div>
          <div class="field-block">
            <label for="officerNameField">Officer Name</label>
            <input id="officerNameField" name="name" value="${escapeHtml(officer.name || "")}">
          </div>
          <div class="field-block">
            <label for="officerRoleField">Role</label>
            <input id="officerRoleField" name="role" value="${escapeHtml(officer.role || "")}">
          </div>
          <div class="field-block">
            <label for="officerDepartmentField">Department</label>
            <input id="officerDepartmentField" name="department" value="${escapeHtml(officer.department || "")}">
          </div>
          <div class="field-block">
            <label for="officerClearanceField">Clearance Level</label>
            <input id="officerClearanceField" name="clearance_level" value="${escapeHtml(officer.clearance_level || "")}">
          </div>
        </div>
        <div class="button-row" style="margin-top:18px">
          <button class="btn btn-primary" type="submit">Save Profile</button>
          <button class="btn btn-secondary" type="button" id="reloadProfileBtn">Reload From Backend</button>
        </div>
      </form>
    </section>
  `;

  document.getElementById("officerProfileForm")?.addEventListener("submit", saveOfficerProfile);
  document.getElementById("reloadProfileBtn")?.addEventListener("click", async () => {
    await hydrateState();
    renderGlobalChrome();
    renderPage();
    showToast("Officer profile reloaded.");
  });
}

async function saveOfficerProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());
  try {
    const response = await fetchJson("/officer-profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    appState.officer = response.profile;
    renderGlobalChrome();
    renderPage();
    showToast("Officer profile saved.");
  } catch (error) {
    showToast(error.message || "Could not save officer profile.");
  }
}

function renderHelpPage() {
  dom.pageRoot.innerHTML = `
    <section class="page-header">
      <h1>Help</h1>
      <p>Quick guidance for using the live procurement workflow without relying on placeholder content.</p>
    </section>

    <section class="grid-2">
      <article class="panel">
        <div class="section-header">
          <div class="section-title">How To Use</div>
        </div>
        <div class="help-list">
          <div class="list-item">1. Open <strong>Upload Tender</strong> and choose the tender PDF plus bidder files.</div>
          <div class="list-item">2. Run the live evaluation. The extracted text panel will show text pulled from those uploaded files.</div>
          <div class="list-item">3. Review criteria, add officer notes, and log accept / reject / original document actions.</div>
          <div class="list-item">4. Use <strong>All Bidders</strong>, <strong>Active Evals</strong>, and <strong>Audit Trail</strong> for live history.</div>
        </div>
      </article>

      <article class="panel">
        <div class="section-header">
          <div class="section-title">Backend Status</div>
        </div>
        <div class="help-list">
          <div class="list-item searchable" data-search-text="${escapeHtml(API_BASE)}">
            <strong>API Base</strong><br>
            <span class="muted">${escapeHtml(API_BASE)}</span>
          </div>
          <div class="list-item">
            <strong>Officer Profile Source</strong><br>
            <span class="muted">${escapeHtml(appState.officer?.source || "Unknown")}</span>
          </div>
          <div class="list-item">
            <strong>Latest Evaluation</strong><br>
            <span class="muted">${escapeHtml(appState.latest ? getDisplayBidderName(appState.latest) : "No live evaluation yet")}</span>
          </div>
        </div>
      </article>
    </section>
  `;
}

function renderAuditList(entries) {
  if (!entries.length) {
    return `<div class="notice">No audit entries available.</div>`;
  }
  return `
    <div class="audit-list">
      ${entries.map((entry) => `
        <div class="audit-item searchable" data-search-text="${escapeHtml(searchBlob(entry.agent, entry.action, entry.result_summary, entry.bidder_name, entry.tender_id))}">
          <div class="audit-title">${escapeHtml(`${entry.agent || "System"} → ${entry.action || "update"}`)}</div>
          <div class="audit-meta">${escapeHtml(entry.result_summary || entry.input_summary || "No summary available")}</div>
          <div class="pill-row" style="margin-top:10px">
            <span class="tag info">${escapeHtml(formatDateTime(entry.timestamp || entry.timestamp_readable))}</span>
            ${entry.bidder_name ? `<span class="tag success">${escapeHtml(entry.bidder_name)}</span>` : ""}
            ${entry.tender_id ? `<span class="tag warning">${escapeHtml(entry.tender_id)}</span>` : ""}
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderProgressRow(label, value, total, tone) {
  const percent = total ? Math.round((value / total) * 100) : 0;
  return `
    <div style="margin-bottom:16px">
      <div class="section-subtitle" style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span>${escapeHtml(label)}</span>
        <span>${escapeHtml(`${value} (${percent}%)`)}</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill ${tone}" style="width:${percent}%"></div>
      </div>
    </div>
  `;
}

async function logOfficerAction(action) {
  if (!appState.latest) {
    showToast("Run a live evaluation first.");
    return;
  }
  const note = document.getElementById("officerNoteInput")?.value?.trim() || action;
  try {
    await fetchJson("/log-officer-action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        officer_id: appState.officer?.officer_id,
        action,
        bidder_name: appState.latest.bidder_name,
        tender_id: appState.latest.tender_id,
        reason: note,
      }),
    });
    await hydrateState();
    renderGlobalChrome();
    renderPage();
    showToast("Officer action logged.");
  } catch (error) {
    showToast(error.message || "Could not log officer action.");
  }
}

function buildCriteria(result) {
  return result?.final_verdict?.criteria_results || [];
}

function getDisplayBidderName(item) {
  const rawName = typeof item === "string" ? item : item?.bidder_name || item?.bidder_profile?.entity_name;
  const cleaned = String(rawName || "").replace(/^[:\s;-]+|[:\s;-]+$/g, "");
  const lowered = cleaned.toLowerCase();
  const invalidNames = new Set(["", "unknown", "date of birth", "dob", "name", "address"]);
  const invalidPhrases = ["date of birth", "standard bidding document", "procurement of civil works"];

  if (cleaned && !invalidNames.has(lowered) && !invalidPhrases.some((phrase) => lowered.includes(phrase))) {
    return cleaned;
  }

  const savedDocument = item?.saved_documents?.[0] || item?.extracted_documents?.[0]?.saved_file;
  const sourceFilename = savedDocument?.original_filename || savedDocument?.stored_filename || item?.extracted_documents?.[0]?.source_filename;
  return bidderLabelFromFilename(sourceFilename);
}

function getRecordDocuments(item) {
  const docs = [];
  if (item?.saved_tender?.saved_url) {
    docs.push({ ...item.saved_tender, label: "Tender" });
  }
  (item?.saved_documents || []).forEach((document, index) => {
    docs.push({ ...document, label: `Doc ${index + 1}` });
  });
  (item?.extracted_documents || []).forEach((document, index) => {
    const savedFile = document.saved_file || null;
    if (savedFile?.saved_url && !docs.some((itemDoc) => itemDoc.saved_url === savedFile.saved_url)) {
      docs.push({ ...savedFile, label: `Doc ${index + 1}` });
    }
  });
  return docs;
}

function renderRecordDocuments(item) {
  const docs = getRecordDocuments(item);
  if (!docs.length) return `<span class="muted">No documents</span>`;
  return `
    <div class="table-doc-links">
      ${docs.slice(0, 4).map((document) => `
        <a class="tag info" href="${escapeHtml(resolveApiResource(document.saved_url))}" target="_blank" rel="noreferrer">
          ${escapeHtml(document.label || document.original_filename || "Document")}
        </a>
      `).join("")}
      ${docs.length > 4 ? `<span class="tag warning">${escapeHtml(`+${docs.length - 4}`)}</span>` : ""}
    </div>
  `;
}

function getDocumentSearchText(item) {
  return getRecordDocuments(item)
    .map((document) => `${document.label || ""} ${document.original_filename || ""} ${document.stored_filename || ""}`)
    .join(" ");
}

function formatBidAmount(amount) {
  const rawValue = String(amount || "").trim();
  if (!rawValue) return "--";
  const numericValue = Number(rawValue.replace(/,/g, ""));
  if (Number.isFinite(numericValue)) {
    return `Rs. ${numericValue.toLocaleString("en-IN")}`;
  }
  return rawValue.startsWith("Rs.") ? rawValue : `Rs. ${rawValue}`;
}

function bidderLabelFromFilename(filename) {
  if (!filename) return "Unidentified bidder";
  const baseName = String(filename).split(/[\\/]/).pop();
  const nameWithoutExt = baseName.replace(/\.[^.]+$/, "");
  const cleaned = nameWithoutExt
    .replace(/^(?:bidder|document|doc|file)[_-]*\d*[_-]*/i, "")
    .replace(/[_-]+/g, " ")
    .trim();

  if (!cleaned) return `Unidentified bidder (${baseName})`;
  return cleaned.replace(/\b\w/g, (char) => char.toUpperCase());
}

function inferDocType(file) {
  const name = file.name.toLowerCase();
  if (name.includes("gst")) return "gst_certificate";
  if (name.includes("pan")) return "pan_card";
  if (name.includes("msme") || name.includes("udyam")) return "msme_certificate";
  if (name.includes("income") || name.includes("itr") || name.includes("tax")) return "income_tax_return";
  if (name.includes("bank") || name.includes("solvency")) return "bank_solvency_certificate";
  if (name.includes("emd")) return "emd_deposit_proof";
  if (name.includes("iso")) return "iso_certificate";
  if (name.includes("experience") || name.includes("contract")) return "experience_certificate";
  return "certificate";
}

function resolveApiResource(path) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

function formatFileSize(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) return "0 KB";
  if (value < 1024 * 1024) return `${Math.ceil(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function getUploadStatusText() {
  if (appState.upload.running) return "Running live evaluation against the backend...";
  if (!appState.upload.tenderFile && !appState.upload.bidderFiles.length) {
    return "Select files to start the live run.";
  }
  if (!appState.upload.tenderFile) return "Tender PDF missing.";
  if (!appState.upload.bidderFiles.length) return "Bidder files missing.";
  return "Files ready. Run the live evaluation.";
}

function renderVerdictTag(verdict) {
  const status = (verdict || "UNKNOWN").toUpperCase();
  const tone = status === "PASS" || status === "MET"
    ? "success"
    : status === "FAIL" || status === "NOT_MET"
      ? "danger"
      : "warning";
  const labelMap = {
    PASS: "Pass",
    FAIL: "Fail",
    REFER_TO_COMMITTEE: "Review",
    MET: "Met",
    NOT_MET: "Not Met",
    CANNOT_VERIFY: "Needs Review",
  };
  return `<span class="tag ${tone}">${escapeHtml(labelMap[status] || status.replaceAll("_", " "))}</span>`;
}

function renderConfidenceTag(confidence) {
  if (confidence == null) return "";
  const percent = Math.round(Number(confidence) * 100);
  const tone = percent >= 85 ? "success" : percent >= 60 ? "warning" : "danger";
  return `<span class="tag ${tone}">${escapeHtml(`${percent}% confidence`)}</span>`;
}

function formatDateTime(rawDate) {
  if (!rawDate) return "Unknown time";
  const parsed = new Date(rawDate);
  if (Number.isNaN(parsed.getTime())) return rawDate;
  return `${parsed.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })} ${parsed.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`;
}

function getInitials(name) {
  return (name || "Officer")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

function truncate(text, limit = 60) {
  if (!text) return "";
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function searchBlob(...parts) {
  return parts.filter(Boolean).join(" ");
}

function applySearchFilter(query) {
  document.querySelectorAll(".searchable").forEach((element) => {
    const haystack = (element.dataset.searchText || "").toLowerCase();
    if (!query || haystack.includes(query)) {
      element.classList.remove("search-hidden");
    } else {
      element.classList.add("search-hidden");
    }
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.style.cssText = "position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1565c0;color:#fff;padding:12px 18px;border-radius:12px;box-shadow:0 12px 24px rgba(0,0,0,0.28);z-index:50;font-weight:700;max-width:720px;text-align:center";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2600);
}
