"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
let currentResults = [];
let autocompleteTimer = null;
let acActiveIndex = -1;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const searchInput     = document.getElementById("search-input");
const autocompleteList = document.getElementById("autocomplete-list");
const btnSearch       = document.getElementById("btn-search");
const dropZone        = document.getElementById("drop-zone");
const fileInput       = document.getElementById("file-input");
const fileNameEl      = document.getElementById("file-name");
const btnUpload       = document.getElementById("btn-upload");
const btnDownload     = document.getElementById("btn-download");
const btnReload       = document.getElementById("btn-reload");
const statusBar       = document.getElementById("status-bar");
const statusText      = document.getElementById("status-text");
const errorBanner     = document.getElementById("error-banner");
const resultsSection  = document.getElementById("results-section");
const resultsSummary  = document.getElementById("results-summary");
const resultsContainer = document.getElementById("results-container");

// ── Helpers ───────────────────────────────────────────────────────────────────
function showStatus(msg) {
  statusText.textContent = msg;
  statusBar.hidden = false;
  errorBanner.hidden = true;
}
function hideStatus() { statusBar.hidden = true; }

function showError(msg) {
  errorBanner.textContent = msg;
  errorBanner.hidden = false;
  hideStatus();
}
function hideError() { errorBanner.hidden = true; }

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function highlightMatch(text, query) {
  if (!query || !text) return escapeHtml(text);
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regex = new RegExp(`(${escaped})`, "gi");
  return escapeHtml(text).replace(regex, "<mark>$1</mark>");
}

function scoreClass(score) {
  if (score >= 90) return "score-high";
  if (score >= 80) return "score-med";
  return "score-low";
}

// ── Render results ─────────────────────────────────────────────────────────────
function renderResults(results) {
  currentResults = results;
  resultsContainer.innerHTML = "";

  if (!results.length) {
    resultsSection.hidden = true;
    return;
  }

  const totalHits = results.reduce((s, r) => s + r.results.length, 0);
  const matched   = results.filter(r => r.results.length > 0).length;
  resultsSummary.textContent =
    `${matched} of ${results.length} quer${results.length !== 1 ? "ies" : "y"} matched — ${totalHits} product${totalHits !== 1 ? "s" : ""} found`;

  results.forEach(item => {
    const group = document.createElement("div");
    group.className = "query-group";

    const label = document.createElement("div");
    label.className = "query-label";
    label.innerHTML = `Query: <span>${escapeHtml(item.query)}</span>`;
    group.appendChild(label);

    if (!item.results.length) {
      const noMatch = document.createElement("p");
      noMatch.className = "no-match";
      noMatch.textContent = "No matching products found.";
      group.appendChild(noMatch);
    } else {
      const wrap  = document.createElement("div");
      wrap.className = "table-wrap";

      const table = document.createElement("table");
      table.innerHTML = `
        <thead>
          <tr>
            <th>Product Name</th>
            <th>Generic Name</th>
            <th>Composition</th>
            <th>Strength</th>
            <th>Dosage Form</th>
            <th>Company</th>
            <th>Score</th>
          </tr>
        </thead>
      `;

      const tbody = document.createElement("tbody");
      item.results.forEach(r => {
        const tr = document.createElement("tr");
        const q  = item.query.toLowerCase();
        tr.innerHTML = `
          <td>${highlightMatch(r.product_name, "")}</td>
          <td>${highlightMatch(r.generic_name, q)}</td>
          <td>${highlightMatch(r.composition, q)}</td>
          <td>${escapeHtml(r.strength)}</td>
          <td>${escapeHtml(r.dosage_form)}</td>
          <td>${escapeHtml(r.company_name)}</td>
          <td><span class="score-badge ${scoreClass(r.score)}">${r.score}%</span></td>
        `;
        tbody.appendChild(tr);
      });

      table.appendChild(tbody);
      wrap.appendChild(table);
      group.appendChild(wrap);
    }

    resultsContainer.appendChild(group);
  });

  resultsSection.hidden = false;
}

// ── Text search ────────────────────────────────────────────────────────────────
async function doSearch() {
  const query = searchInput.value.trim();
  if (!query) { showError("Please enter at least one generic or molecule name."); return; }

  hideError();
  showStatus("Searching…");
  closeAutocomplete();

  try {
    const res  = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    if (!res.ok) { showError(data.error || "Search failed."); return; }
    hideStatus();
    renderResults(data.results);
  } catch {
    showError("Network error — is the server running?");
  }
}

btnSearch.addEventListener("click", doSearch);
searchInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && acActiveIndex === -1) doSearch();
});

// ── Autocomplete ───────────────────────────────────────────────────────────────
function closeAutocomplete() {
  autocompleteList.hidden = true;
  acActiveIndex = -1;
}

searchInput.addEventListener("input", () => {
  clearTimeout(autocompleteTimer);
  const parts = searchInput.value.split(",");
  const current = parts[parts.length - 1].trim();

  if (current.length < 2) { closeAutocomplete(); return; }

  autocompleteTimer = setTimeout(async () => {
    try {
      const res  = await fetch(`/api/autocomplete?q=${encodeURIComponent(current)}`);
      const list = await res.json();
      if (!list.length) { closeAutocomplete(); return; }

      autocompleteList.innerHTML = "";
      list.forEach((name, i) => {
        const li = document.createElement("li");
        li.innerHTML = highlightMatch(name, current);
        li.dataset.value = name;
        li.addEventListener("mousedown", () => selectSuggestion(name));
        autocompleteList.appendChild(li);
      });
      acActiveIndex = -1;
      autocompleteList.hidden = false;
    } catch { /* ignore */ }
  }, 220);
});

function selectSuggestion(name) {
  const parts = searchInput.value.split(",");
  parts[parts.length - 1] = " " + name;
  searchInput.value = parts.join(",").replace(/^\s*,/, "");
  closeAutocomplete();
  searchInput.focus();
}

searchInput.addEventListener("keydown", e => {
  const items = [...autocompleteList.querySelectorAll("li")];
  if (!items.length || autocompleteList.hidden) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    acActiveIndex = (acActiveIndex + 1) % items.length;
    items.forEach((li, i) => li.classList.toggle("active", i === acActiveIndex));
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    acActiveIndex = (acActiveIndex - 1 + items.length) % items.length;
    items.forEach((li, i) => li.classList.toggle("active", i === acActiveIndex));
  } else if (e.key === "Enter" && acActiveIndex >= 0) {
    e.preventDefault();
    selectSuggestion(items[acActiveIndex].dataset.value);
  } else if (e.key === "Escape") {
    closeAutocomplete();
  }
});

document.addEventListener("click", e => {
  if (!autocompleteList.contains(e.target) && e.target !== searchInput) closeAutocomplete();
});

// ── File upload ────────────────────────────────────────────────────────────────
let selectedFile = null;

function setFile(file) {
  if (!file) return;
  selectedFile = file;
  fileNameEl.textContent = file.name;
  btnUpload.disabled = false;
}

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") fileInput.click(); });
fileInput.addEventListener("change", () => setFile(fileInput.files[0]));

dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("dragging"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("dragging");
  const file = e.dataTransfer.files[0];
  if (file) setFile(file);
});

btnUpload.addEventListener("click", async () => {
  if (!selectedFile) return;

  hideError();
  showStatus(`Uploading ${selectedFile.name}…`);

  const form = new FormData();
  form.append("file", selectedFile);

  try {
    const res  = await fetch("/api/upload", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) { showError(data.error || "Upload failed."); return; }
    hideStatus();
    renderResults(data.results);
  } catch {
    showError("Network error — is the server running?");
  }
});

// ── Download ───────────────────────────────────────────────────────────────────
btnDownload.addEventListener("click", async () => {
  if (!currentResults.length) return;

  try {
    const res  = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ results: currentResults }),
    });
    if (!res.ok) { showError("Download failed."); return; }

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = "pharma_search_results.csv";
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    showError("Download error.");
  }
});

// ── Reload dataset ─────────────────────────────────────────────────────────────
btnReload.addEventListener("click", async () => {
  btnReload.disabled = true;
  try {
    const res  = await fetch("/api/reload", { method: "POST" });
    const data = await res.json();
    if (!res.ok) { showError(data.error || "Reload failed."); return; }
    const infoEl = document.getElementById("dataset-info");
    if (infoEl) infoEl.textContent = `Dataset: ${data.product_count} products`;
    showStatus(`Dataset reloaded — ${data.product_count} products loaded.`);
    setTimeout(hideStatus, 3000);
  } catch {
    showError("Could not reload dataset.");
  } finally {
    btnReload.disabled = false;
  }
});
