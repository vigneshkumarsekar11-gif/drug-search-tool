import re
import pandas as pd
from rapidfuzz import fuzz
from data_handler import DataHandler

SEARCH_COLS = ["generic_name_norm", "molecule_name_norm", "composition_norm"]
OUTPUT_COLS = [
    "product_name", "generic_name", "molecule_name",
    "composition", "strength", "dosage_form", "company_name"
]


class PharmSearch:
    def __init__(self, data_handler: DataHandler):
        self.data_handler = data_handler

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", str(text).lower().strip())

    def search_single(self, query: str, fuzzy_threshold: int = 72) -> list[dict]:
        df = self.data_handler.df
        if df is None or df.empty:
            return []

        norm_query = self._normalize(query)
        results = []
        seen = set()

        for _, row in df.iterrows():
            best_score = 0
            matched_field = ""

            for col in SEARCH_COLS:
                cell = row.get(col, "")
                if not cell:
                    continue

                # Substring match gets full score
                if norm_query in cell or cell in norm_query:
                    score = 100
                else:
                    score = fuzz.partial_ratio(norm_query, cell)

                if score > best_score:
                    best_score = score
                    matched_field = col.replace("_norm", "")

            if best_score < fuzzy_threshold:
                continue

            # Deduplicate by product name + strength
            key = f"{row.get('product_name','')}|{row.get('strength','')}"
            if key in seen:
                continue
            seen.add(key)

            entry = {col: row.get(col, "") for col in OUTPUT_COLS}
            entry["score"] = best_score
            entry["matched_field"] = matched_field
            results.append(entry)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def search_multiple(self, queries: list[str]) -> list[dict]:
        return [{"query": q, "results": self.search_single(q)} for q in queries]

    def get_suggestions(self, query: str, limit: int = 10) -> list[str]:
        norm_query = self._normalize(query)
        matches = []

        for name in self.data_handler.all_names:
            norm_name = self._normalize(name)
            if norm_query in norm_name:
                matches.append(name)
                if len(matches) >= limit:
                    break

        return sorted(matches)
