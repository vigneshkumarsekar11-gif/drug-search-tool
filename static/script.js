/* script.js v5 — no full-page spinner; client-side Excel export via SheetJS */
'use strict';

/* ── DOM refs ─────────────────────────────────────────────── */
const $ = id => document.getElementById(id);

const singleInput   = $('single-input');
const acList        = $('autocomplete-list');
const searchBtn     = $('single-search-btn');
const btnIcon       = $('btn-icon');
const btnText       = $('btn-text');
const searchStatus  = $('search-status');

const batchBtn      = $('batch-search-btn');
const batchBtnIcon  = $('batch-btn-icon');
const batchBtnText  = $('batch-btn-text');
const batchStatus   = $('batch-status');
const dropzone      = $('dropzone');
const fileInput     = $('file-input');
const dropFilename  = $('dropzone-filename');

const resultsSection = $('results-section');
const resultsTitle   = $('results-title');
const tbody          = $('results-tbody');
const downloadBtn    = $('download-btn');
const reloadBtn      = $('reload-btn');
const toast          = $('toast');
const statsBadge     = $('stats-badge');
const noResults      = $('no-results-msg');
const resultsFilter  = $('results-filter');
const matchFilter    = $('match-filter');

/* ── State ────────────────────────────────────────────────── */
let allResults = [];
let acTimer    = null;
let acSelected = -1;
let batchFile  = null;

/* ── SVG helpers ──────────────────────────────────────────── */
const ICON_SEARCH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;
const ICON_SPIN   = `<svg class="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2a10 10 0 1 0 10 10" stroke-linecap="round"/></svg>`;

/* ── Fetch with timeout ───────────────────────────────────── */
function apiFetch(url, options = {}, ms = 15000) {
  const ctrl = new AbortController();
  const tid  = setTimeout(() => ctrl.abort(), ms);
  return fetch(url, { ...options, signal: ctrl.signal })
    .finally(() => clearTimeout(tid));
}

/* ── Tab switching ────────────────────────────────────────── */
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $('tab-' + btn.dataset.tab).classList.add('active');
    hideAc();
  });
});

/* ── Toast ────────────────────────────────────────────────── */
let toastTid;
function showToast(msg, type = '') {
  toast.textContent = msg;
  toast.className = 'toast show' + (type ? ' toast-' + type : '');
  clearTimeout(toastTid);
  toastTid = setTimeout(() => toast.classList.remove('show'), 4000);
}

/* ── Inline status bar ────────────────────────────────────── */
function setStatus(el, msg, type = '') {
  if (!msg) { el.hidden = true; el.textContent = ''; return; }
  el.textContent = msg;
  el.className = 'search-status' + (type ? ' status-' + type : '');
  el.hidden = false;
}

/* ── Button loading state ─────────────────────────────────── */
function setBtnLoading(on) {
  searchBtn.disabled = on;
  btnIcon.innerHTML  = on ? ICON_SPIN : ICON_SEARCH;
  btnText.textContent = on ? 'Searching…' : 'Search';
}

function setBatchBtnLoading(on) {
  batchBtn.disabled    = on || !batchFile;
  batchBtnIcon.innerHTML  = on ? ICON_SPIN : ICON_SEARCH;
  batchBtnText.textContent = on ? 'Searching…' : 'Search Batch';
}

/* ── Stats badge ──────────────────────────────────────────── */
async function fetchStats(attempt = 1) {
  try {
    const r = await apiFetch('/stats', {}, 8000);
    if (!r.ok) throw new Error('bad status');
    const d = await r.json();
    statsBadge.textContent = `${d.drug_entries.toLocaleString()} drugs · ${d.product_entries.toLocaleString()} products`;
    statsBadge.classList.remove('badge-error');
  } catch {
    if (attempt <= 6) {
      statsBadge.textContent = `Starting… (${attempt}/6)`;
      setTimeout(() => fetchStats(attempt + 1), 3000);
    } else {
      statsBadge.textContent = 'Server offline';
      statsBadge.classList.add('badge-error');
    }
  }
}
fetchStats();

/* ── Autocomplete ─────────────────────────────────────────── */
function hideAc() { acList.hidden = true; acSelected = -1; }

function renderAc(items, q) {
  if (!items.length) { hideAc(); return; }
  acList.innerHTML = items.map((item, i) =>
    `<li data-idx="${i}">${item.replace(new RegExp(`(${escRe(q)})`, 'gi'), '<mark>$1</mark>')}</li>`
  ).join('');
  acList.hidden = false;
  acSelected = -1;
  acList.querySelectorAll('li').forEach(li =>
    li.addEventListener('mousedown', e => {
      e.preventDefault();
      singleInput.value = items[+li.dataset.idx];
      hideAc();
      doSearch();
    })
  );
}

singleInput.addEventListener('input', () => {
  clearTimeout(acTimer);
  const q = singleInput.value.trim();
  if (q.length < 2) { hideAc(); return; }
  acTimer = setTimeout(async () => {
    try {
      const r = await apiFetch('/autocomplete?q=' + encodeURIComponent(q), {}, 5000);
      renderAc(await r.json(), q);
    } catch { hideAc(); }
  }, 250);
});

singleInput.addEventListener('keydown', e => {
  const items = acList.querySelectorAll('li');
  if (e.key === 'ArrowDown')  { e.preventDefault(); acSelected = Math.min(acSelected + 1, items.length - 1); hilightAc(items); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); acSelected = Math.max(acSelected - 1, -1); hilightAc(items); }
  else if (e.key === 'Enter') { if (acSelected >= 0) { singleInput.value = items[acSelected].textContent; hideAc(); } doSearch(); }
  else if (e.key === 'Escape') hideAc();
});

function hilightAc(items) {
  items.forEach((li, i) => li.classList.toggle('active', i === acSelected));
  if (acSelected >= 0) items[acSelected].scrollIntoView({ block: 'nearest' });
}

document.addEventListener('click', e => {
  if (!singleInput.contains(e.target) && !acList.contains(e.target)) hideAc();
});

/* ── Single search ────────────────────────────────────────── */
searchBtn.addEventListener('click', doSearch);

async function doSearch() {
  hideAc();
  const query = singleInput.value.trim();
  if (!query) { setStatus(searchStatus, 'Please enter a drug name to search.', 'warn'); return; }

  setBtnLoading(true);
  setStatus(searchStatus, 'Searching…');

  try {
    const r = await apiFetch('/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    }, 15000);

    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      setStatus(searchStatus, e.error || 'Server returned an error.', 'error');
      return;
    }

    const d = await r.json();
    allResults = d.results;
    setStatus(searchStatus, ''); // clear
    renderResults(`Results for "${query}" — ${d.count} match${d.count !== 1 ? 'es' : ''} found`);
    if (d.count === 0) setStatus(searchStatus, 'No matches found. Try a different spelling.', 'warn');

  } catch (err) {
    const msg = err.name === 'AbortError'
      ? 'Search timed out (15s). The server may be slow — try again.'
      : 'Cannot reach server. Is the cmd window (run_server.bat) still open?';
    setStatus(searchStatus, msg, 'error');
  } finally {
    setBtnLoading(false);
  }
}

/* ── File upload / drag-drop ──────────────────────────────── */
dropzone.addEventListener('dragover',  e => { e.preventDefault(); dropzone.classList.add('drag-over'); });
dropzone.addEventListener('dragleave', ()  => dropzone.classList.remove('drag-over'));
dropzone.addEventListener('drop', e => {
  e.preventDefault(); dropzone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
});
dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });
fileInput.addEventListener('change', () => { if (fileInput.files[0]) setFile(fileInput.files[0]); });

function setFile(f) {
  batchFile = f;
  dropFilename.textContent = `📄 ${f.name}  (${(f.size / 1024).toFixed(1)} KB)`;
  batchBtn.disabled = false;
}

/* ── Batch search ─────────────────────────────────────────── */
batchBtn.addEventListener('click', async () => {
  if (!batchFile) { setStatus(batchStatus, 'Please upload a file first.', 'warn'); return; }
  const form = new FormData();
  form.append('file', batchFile);

  setBatchBtnLoading(true);
  setStatus(batchStatus, 'Processing file…');

  try {
    const r = await apiFetch('/batch', { method: 'POST', body: form }, 60000);
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      setStatus(batchStatus, e.error || 'Batch search failed.', 'error');
      return;
    }
    const d = await r.json();
    allResults = d.results;
    setStatus(batchStatus, '');
    renderResults(`Batch — ${d.queries} queries · ${d.count} rows`);
  } catch (err) {
    const msg = err.name === 'AbortError'
      ? 'Batch timed out (60s). Try a smaller file.'
      : 'Cannot reach server. Is the cmd window (run_server.bat) still open?';
    setStatus(batchStatus, msg, 'error');
  } finally {
    setBatchBtnLoading(false);
  }
});

/* ── Results ──────────────────────────────────────────────── */
function renderResults(title) {
  resultsTitle.textContent = title;
  resultsSection.hidden = false;
  resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  applyFilters();
}

function applyFilters() {
  const tq = resultsFilter.value.toLowerCase();
  const mq = matchFilter.value;
  const filtered = allResults.filter(r => {
    if (mq && r.match_type !== mq) return false;
    if (tq) return [r.query, r.brand, r.molecules, r.strength, r.dosage_form].join(' ').toLowerCase().includes(tq);
    return true;
  });

  tbody.innerHTML = '';
  noResults.hidden = filtered.length > 0;

  filtered.forEach((r, i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="row-num">${i + 1}</td>
      <td><strong>${esc(r.query)}</strong></td>
      <td>${r.brand ? `<strong>${hilite(esc(r.brand), r.query)}</strong>` : '<em style="color:var(--text-muted)">—</em>'}</td>
      <td>${hilite(esc(r.molecules), r.query)}</td>
      <td>${esc(r.strength)}</td>
      <td>${esc(r.dosage_form)}</td>
      <td>${badge(r.match_type)}</td>
      <td>${scoreBar(r.score, r.match_type)}</td>`;
    tbody.appendChild(tr);
  });
}

resultsFilter.addEventListener('input',  applyFilters);
matchFilter.addEventListener('change', applyFilters);

/* ── Download (client-side via SheetJS — works on Vercel) ─── */
downloadBtn.addEventListener('click', () => {
  if (!allResults.length) { showToast('No results to download yet.', ''); return; }
  const rows = allResults.map(r => ({
    'Input Query':        r.query,
    'Product Name':       r.brand,
    'Molecules':          r.molecules,
    'Strength':           r.strength,
    'Dosage Form':        r.dosage_form,
    'Match Type':         r.match_type,
    'Confidence Score':   r.score,
    'Source':             r.sheet,
  }));
  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.json_to_sheet(rows);
  // Auto column widths
  ws['!cols'] = Object.keys(rows[0]).map(k => ({ wch: Math.max(k.length, 16) }));
  XLSX.utils.book_append_sheet(wb, ws, 'Search Results');
  XLSX.writeFile(wb, 'pharma_search_results.xlsx');
});

/* ── Reload data ──────────────────────────────────────────── */
reloadBtn.addEventListener('click', async () => {
  reloadBtn.disabled = true;
  reloadBtn.textContent = 'Reloading…';
  try {
    const r = await apiFetch('/reload', { method: 'POST' }, 60000);
    const d = await r.json();
    if (r.ok) { showToast(`Reloaded: ${d.drug_entries} drugs, ${d.product_entries} products`, 'success'); fetchStats(); }
    else showToast(d.error || 'Reload failed.', 'error');
  } catch { showToast('Reload failed — check the server window.', 'error'); }
  finally {
    reloadBtn.disabled = false;
    reloadBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg> Reload Data`;
  }
});

/* ── Helpers ──────────────────────────────────────────────── */
function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'); }
function hilite(text, q) {
  if (!q || !text) return text;
  q.toLowerCase().split(/\s+/).filter(w => w.length >= 3).forEach(w => {
    text = text.replace(new RegExp(`(${escRe(w)})`, 'gi'), '<mark class="hit">$1</mark>');
  });
  return text;
}
function badge(type) {
  const cls = { exact:'badge-exact', partial:'badge-partial', fuzzy:'badge-fuzzy', 'no match':'badge-nomatch' }[type] || '';
  return `<span class="badge ${cls}">${esc(type)}</span>`;
}
function scoreBar(score, type) {
  if (type === 'no match') return '<span style="color:var(--text-muted)">—</span>';
  const pct   = Math.round(score);
  const color = score >= 95 ? '#16a34a' : score >= 80 ? '#2563eb' : '#d97706';
  return `<div class="score-bar-wrap"><div class="score-bar"><div class="score-bar-fill" style="width:${pct}%;background:${color}"></div></div><span class="score-num">${pct}</span></div>`;
}
