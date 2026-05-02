"""
data_loader.py
Loads drug/product data.

Production (Vercel): reads pre-built JSON files in data/
Local dev:           falls back to PDF + Excel if JSON files are missing,
                     or call export_data.py to regenerate them.
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "data")
DRUG_JSON   = os.path.join(DATA_DIR, "drug_data.json")
PRODUCT_JSON= os.path.join(DATA_DIR, "product_data.json")

# Local-dev source files (not needed on Vercel)
PDF_PATH   = os.environ.get("DRUG_LIST_PDF",   r"C:\Users\blude\Videos\DRUG LIST.pdf")
EXCEL_PATH = os.environ.get("PRODUCTS_XLSX",   r"C:\Users\blude\Videos\products.xlsx")

# ── Cache ──────────────────────────────────────────────────────────────────────
_drug_list:    list[dict] | None = None
_product_list: list[dict] | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────
def normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s\+\-/]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ── JSON loaders (production path) ────────────────────────────────────────────
def _load_from_json() -> tuple[list[dict], list[dict]]:
    logger.info("Loading data from pre-built JSON files…")
    with open(DRUG_JSON,    encoding="utf-8") as f:
        drugs = json.load(f)
    with open(PRODUCT_JSON, encoding="utf-8") as f:
        products = json.load(f)
    logger.info("JSON loaded: %d drugs, %d products", len(drugs), len(products))
    return drugs, products


# ── PDF / Excel loaders (local dev fallback) ──────────────────────────────────
def _load_from_sources() -> tuple[list[dict], list[dict]]:
    try:
        import pdfplumber
        import pandas as pd
    except ImportError:
        raise RuntimeError(
            "pdfplumber / pandas not installed. "
            "Run export_data.py locally to generate the JSON data files, "
            "then commit them to the repo."
        )

    logger.info("Loading PDF: %s", PDF_PATH)
    drugs = []
    with pdfplumber.open(PDF_PATH) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                for row in table:
                    if not row or not row[0]:
                        continue
                    if str(row[0]).strip().upper() in ("S.NO", "S NO", "SNO"):
                        continue
                    if str(row[0]).strip().isdigit():
                        c = [
                            re.sub(r"\s+", " ", str(x).strip()) if x else ""
                            for x in row[:9]
                        ]
                        while len(c) < 9:
                            c.append("")
                        drugs.append({
                            "generic_name":    c[2],
                            "form":            c[3],
                            "strength":        c[4],
                            "measure":         c[5],
                            "unit_of_measure": c[6],
                            "strength_full":   (c[4] + " " + c[5] + " " + c[6]).strip(),
                            "norm_generic":    normalize(c[2]),
                        })
    logger.info("PDF loaded: %d drugs", len(drugs))

    logger.info("Loading Excel: %s", EXCEL_PATH)
    df = pd.read_excel(EXCEL_PATH, sheet_name="MAIN", dtype=str)
    df.columns = [col.strip() for col in df.columns]
    df = df.rename(columns={
        "Brand": "brand", "Composition": "composition",
        "Molecules": "molecules", "Strength": "strength",
        "Dosage Form": "dosage_form", "Status": "status",
    })
    df = df.fillna("")
    df = df[df["brand"].str.strip().str.len() > 0].copy()
    df["norm_molecules"]   = df["molecules"].apply(normalize)
    df["norm_composition"] = df["composition"].apply(normalize)
    df["norm_brand"]       = df["brand"].apply(normalize)
    df["sheet"] = "MAIN"
    products = df[[
        "brand", "molecules", "composition", "strength",
        "dosage_form", "sheet", "norm_molecules", "norm_composition", "norm_brand",
    ]].to_dict("records")
    logger.info("Excel loaded: %d products", len(products))
    return drugs, products


# ── Public API ────────────────────────────────────────────────────────────────
def load_data(force: bool = False) -> tuple[list[dict], list[dict]]:
    global _drug_list, _product_list
    if force or _drug_list is None:
        if os.path.exists(DRUG_JSON) and os.path.exists(PRODUCT_JSON):
            _drug_list, _product_list = _load_from_json()
        else:
            _drug_list, _product_list = _load_from_sources()
    return _drug_list, _product_list


def reload() -> tuple[list[dict], list[dict]]:
    return load_data(force=True)


def get_all_generic_names() -> list[str]:
    drugs, _ = load_data()
    seen = set()
    out = []
    for d in drugs:
        n = d.get("generic_name", "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return sorted(out)


def get_all_molecule_names() -> list[str]:
    _, products = load_data()
    mols = set()
    for p in products:
        for part in re.split(r"[+\n]", p.get("molecules", "")):
            m = re.sub(r"\d[\d\s\.]*\s*(mg|ml|mcg|iu|g|%|gm)\b.*", "", part, flags=re.I).strip()
            if len(m) > 2:
                mols.add(m.title())
    return sorted(mols)
