"""
data_loader.py — Load and preprocess drug list PDF and products Excel.
Results are cached in memory; call reload() to refresh after file changes.
"""

import re
import os
import logging
import pdfplumber
import pandas as pd

logger = logging.getLogger(__name__)

# Paths — override via environment variables if needed
PDF_PATH = os.environ.get(
    "DRUG_LIST_PDF",
    r"C:\Users\blude\Videos\DRUG LIST.pdf",
)
EXCEL_PATH = os.environ.get(
    "PRODUCTS_XLSX",
    r"C:\Users\blude\Videos\products.xlsx",
)

# ── internal cache ──────────────────────────────────────────────────────────
_drug_df: pd.DataFrame | None = None
_product_df: pd.DataFrame | None = None


# ── text helpers ─────────────────────────────────────────────────────────────
def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip non-alphanumeric (keep spaces)."""
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s\+\-/]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ── PDF loader ────────────────────────────────────────────────────────────────
def _load_pdf() -> pd.DataFrame:
    """Extract all rows from the drug-list PDF and return a clean DataFrame."""
    rows = []
    expected_cols = [
        "s_no", "quote_item_id", "generic_name",
        "form", "strength", "measure", "unit_of_measure",
        "avg_consumption", "form_type",
    ]

    logger.info("Loading PDF: %s", PDF_PATH)
    with pdfplumber.open(PDF_PATH) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                for row in table:
                    # Skip header rows
                    if row and row[0] and str(row[0]).strip().upper() in ("S.NO", "S NO", "SNO"):
                        continue
                    if len(row) >= 3 and row[0] and str(row[0]).strip().isdigit():
                        # Clean each cell
                        cleaned = [
                            re.sub(r"\s+", " ", str(c).strip()) if c else ""
                            for c in row[:9]
                        ]
                        # Pad to 9 cols
                        while len(cleaned) < 9:
                            cleaned.append("")
                        rows.append(cleaned)

    df = pd.DataFrame(rows, columns=expected_cols)

    # Build composite strength string e.g. "200 mg"
    df["strength_full"] = (
        df["strength"].str.strip() + " " + df["measure"].str.strip() + " " + df["unit_of_measure"].str.strip()
    ).str.strip()
    df["strength_full"] = df["strength_full"].apply(
        lambda x: re.sub(r"\s+", " ", x).strip()
    )

    # Normalized search key
    df["norm_generic"] = df["generic_name"].apply(normalize)

    logger.info("PDF loaded: %d drug entries", len(df))
    return df


# ── Excel loader ──────────────────────────────────────────────────────────────
def _load_excel() -> pd.DataFrame:
    """Load the MAIN products sheet (and New Launch) from the Excel file."""
    logger.info("Loading Excel: %s", EXCEL_PATH)
    frames = []

    # MAIN sheet
    df_main = pd.read_excel(EXCEL_PATH, sheet_name="MAIN", dtype=str)
    # Strip whitespace from column names before renaming
    df_main.columns = [c.strip() for c in df_main.columns]
    df_main = df_main.rename(columns={
        "Brand": "brand",          # stripped from "Brand "
        "Composition": "composition",
        "Molecules": "molecules",
        "Strength": "strength",
        "Dosage Form": "dosage_form",
        "Marketing division": "division",
        "Product Code": "product_code",
        "MRP": "mrp",
        "Status": "status",
    })
    df_main["sheet"] = "MAIN"
    frames.append(df_main)

    # New Launch sheet (different layout — detect brand column)
    try:
        df_new = pd.read_excel(EXCEL_PATH, sheet_name="New Launch Products", header=1, dtype=str)
        df_new.columns = [str(c).strip() for c in df_new.columns]
        # Find the brand-like column
        brand_col = next(
            (c for c in df_new.columns if "brand" in c.lower() or c.strip() == "Brand"),
            None,
        )
        if brand_col:
            df_new = df_new.rename(columns={brand_col: "brand"})
            comp_col = next((c for c in df_new.columns if "comp" in c.lower()), None)
            mol_col  = next((c for c in df_new.columns if "mol"  in c.lower()), None)
            if comp_col:
                df_new = df_new.rename(columns={comp_col: "composition"})
            if mol_col:
                df_new = df_new.rename(columns={mol_col: "molecules"})
            df_new["sheet"] = "New Launch"
            frames.append(df_new)
    except Exception as exc:
        logger.warning("Could not load New Launch sheet: %s", exc)

    df = pd.concat(frames, ignore_index=True, sort=False)

    # Ensure required columns exist
    for col in ("brand", "composition", "molecules", "strength", "dosage_form", "sheet"):
        if col not in df.columns:
            df[col] = ""

    # Fill NaN
    df = df.fillna("")

    # Clean brand names
    df["brand"] = df["brand"].str.strip()
    df = df[df["brand"].str.len() > 0].copy()

    # Normalized search keys
    df["norm_molecules"]   = df["molecules"].apply(normalize)
    df["norm_composition"] = df["composition"].apply(normalize)
    df["norm_brand"]       = df["brand"].apply(normalize)

    logger.info("Excel loaded: %d product entries", len(df))
    return df


# ── public API ────────────────────────────────────────────────────────────────
def load_data(force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (drug_df, product_df), loading from disk only once unless forced."""
    global _drug_df, _product_df

    if force or _drug_df is None:
        _drug_df = _load_pdf()
    if force or _product_df is None:
        _product_df = _load_excel()

    return _drug_df, _product_df


def reload() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Force reload from disk (call after replacing source files)."""
    return load_data(force=True)


def get_all_generic_names() -> list[str]:
    """Return sorted unique generic names for autocomplete."""
    drug_df, _ = load_data()
    return sorted(drug_df["generic_name"].dropna().unique().tolist())


def get_all_molecule_names() -> list[str]:
    """Return sorted unique molecule fragments for autocomplete."""
    _, product_df = load_data()
    mols = set()
    for val in product_df["molecules"].dropna():
        for part in re.split(r"[+\n]", val):
            m = re.sub(r"\d[\d\s\.]*\s*(mg|ml|mcg|iu|g|%|gm)\b.*", "", part, flags=re.I).strip()
            if len(m) > 2:
                mols.add(m.title())
    return sorted(mols)
