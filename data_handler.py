import pandas as pd
import os
import re
import logging

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = [
    "product_name", "generic_name", "molecule_name",
    "composition", "strength", "dosage_form", "company_name"
]

UPLOAD_HINT_KEYWORDS = ["generic", "molecule", "name", "drug", "composition", "ingredient"]


class DataHandler:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.df: pd.DataFrame = pd.DataFrame()
        self.load()

    def load(self):
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Dataset not found at: {self.filepath}")

        ext = os.path.splitext(self.filepath)[1].lower()
        if ext == ".csv":
            self.df = pd.read_csv(self.filepath, dtype=str)
        elif ext in (".xlsx", ".xls"):
            self.df = pd.read_excel(self.filepath, dtype=str)
        else:
            raise ValueError(f"Unsupported dataset format: {ext}")

        self.df.columns = [c.strip().lower().replace(" ", "_") for c in self.df.columns]
        self.df.fillna("", inplace=True)
        self._add_normalized_columns()
        logger.info(f"Loaded {len(self.df)} products from {self.filepath}")

    def reload(self):
        self.load()

    def _add_normalized_columns(self):
        for col in ["generic_name", "molecule_name", "composition"]:
            if col in self.df.columns:
                self.df[f"{col}_norm"] = self.df[col].apply(self._normalize)

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", str(text).lower().strip())

    def parse_upload(self, file) -> list[str]:
        """Parse an uploaded CSV/XLSX file and return a list of query strings."""
        filename = file.filename.lower()
        if filename.endswith(".csv"):
            df = pd.read_csv(file, dtype=str)
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file, dtype=str)
        else:
            raise ValueError("Unsupported format. Please upload a CSV or XLSX file.")

        if df.empty:
            raise ValueError("The uploaded file is empty.")

        # Auto-detect the target column by name hint, else use first column
        target_col = df.columns[0]
        for col in df.columns:
            if any(kw in col.lower() for kw in UPLOAD_HINT_KEYWORDS):
                target_col = col
                break

        queries = (
            df[target_col]
            .dropna()
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .tolist()
        )

        if not queries:
            raise ValueError("No valid entries found in the uploaded file.")

        return queries

    @property
    def all_names(self) -> list[str]:
        """Return unique generic and molecule names for autocomplete."""
        names = set()
        for col in ["generic_name", "molecule_name"]:
            if col in self.df.columns:
                names.update(self.df[col].dropna().unique())
        return sorted(n for n in names if n)
