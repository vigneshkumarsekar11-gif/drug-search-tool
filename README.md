# Pharma Product Search

A lightweight Flask web app for searching pharmaceutical products by generic name, molecule, or composition.

---

## Quick Start

```bash
cd pharma_search
pip install -r requirements.txt
python web.py
```

Then open **http://localhost:5000** in your browser.

---

## Requirements

- Python 3.10+
- Source files at their default paths (configurable via env vars — see below)

---

## File Structure

```
pharma_search/
├── web.py            # Flask routes
├── data_loader.py    # PDF + Excel ingestion & caching
├── matcher.py        # Exact / partial / fuzzy matching
├── requirements.txt
├── templates/
│   └── index.html    # Single-page UI
└── static/
    ├── style.css
    └── script.js
```

---

## Data File Paths

| File | Default location | Env variable to override |
|------|-----------------|--------------------------|
| Drug list PDF | `C:\Users\blude\Videos\DRUG LIST.pdf` | `DRUG_LIST_PDF` |
| Products Excel | `C:\Users\blude\Videos\products.xlsx` | `PRODUCTS_XLSX` |

**To change paths:**

```bash
# Windows
set DRUG_LIST_PDF=C:\path\to\your\druglist.pdf
set PRODUCTS_XLSX=C:\path\to\your\products.xlsx
python web.py

# Or on Linux/Mac
DRUG_LIST_PDF=/data/druglist.pdf PRODUCTS_XLSX=/data/products.xlsx python web.py
```

---

## Replacing Source Files

1. Drop the new PDF or Excel file in place (same filename), **or** set the env vars to the new path.
2. Click **"Reload Data"** in the top-right of the UI — no server restart needed.

---

## Features

| Feature | Detail |
|---------|--------|
| Single search | Type any generic/molecule name, partial name, or combination |
| Autocomplete | Suggestions appear after 2 characters |
| Batch upload | CSV / TXT (one per line) or XLSX (first column) |
| Match types | Exact → Partial → Fuzzy (rapidfuzz WRatio ≥ 70) |
| Download | Excel export of current results |
| Live filter | Filter results table by text or match type |
| Reload | Hot-reload data without restarting the server |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/search` | `{"query": "Amlodipine"}` → JSON results |
| `POST` | `/batch` | multipart file upload → JSON results |
| `GET` | `/autocomplete?q=amlo` | JSON list of suggestions |
| `GET` | `/download` | Download last results as Excel |
| `POST` | `/reload` | Force reload source files |
| `GET` | `/stats` | `{"drug_entries": N, "product_entries": N}` |
