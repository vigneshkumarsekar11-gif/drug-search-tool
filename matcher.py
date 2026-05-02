"""
matcher.py — Fuzzy / partial / exact matching between search queries and
drug/product datasets.

Match pipeline (in priority order):
  1. Exact match on normalized generic name or molecule
  2. Partial (substring) match
  3. Fuzzy match via rapidfuzz (WRatio ≥ threshold)
"""

import re
from dataclasses import dataclass, field

import pandas as pd
from rapidfuzz import fuzz, process

from data_loader import load_data, normalize

FUZZY_THRESHOLD = 70   # minimum score to accept as fuzzy match


@dataclass
class MatchResult:
    query: str
    brand: str
    molecules: str
    strength: str
    dosage_form: str
    match_type: str        # "exact" | "partial" | "fuzzy"
    score: int             # 100 = exact, else rapidfuzz WRatio
    sheet: str = ""
    composition: str = ""
    highlight_indices: list[tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query":       self.query,
            "brand":       self.brand,
            "molecules":   self.molecules,
            "strength":    self.strength,
            "dosage_form": self.dosage_form,
            "match_type":  self.match_type,
            "score":       self.score,
            "sheet":       self.sheet,
        }


# ── helpers ───────────────────────────────────────────────────────────────────
def _highlight_span(text: str, query: str) -> list[tuple[int, int]]:
    """Return (start, end) spans where query appears in text (case-insensitive)."""
    spans = []
    q = query.lower()
    t = text.lower()
    start = 0
    while True:
        idx = t.find(q, start)
        if idx == -1:
            break
        spans.append((idx, idx + len(q)))
        start = idx + 1
    return spans


def _build_candidate_map(product_df: pd.DataFrame) -> dict[str, list[int]]:
    """Map normalized molecule tokens → row indices for fast pre-filtering."""
    token_map: dict[str, list[int]] = {}
    for idx, row in product_df.iterrows():
        key = (row["norm_molecules"] + " " + row["norm_composition"]).strip()
        # Index each word of length ≥ 3
        for token in key.split():
            if len(token) >= 3:
                token_map.setdefault(token, []).append(idx)
    return token_map


# pre-built at first search call
_candidate_map: dict[str, list[int]] | None = None


def _get_candidate_rows(query_norm: str, product_df: pd.DataFrame) -> pd.DataFrame:
    global _candidate_map
    if _candidate_map is None:
        _candidate_map = _build_candidate_map(product_df)

    tokens = [t for t in query_norm.split() if len(t) >= 3]
    if not tokens:
        return product_df

    # Union of rows matching any token
    candidate_idx: set[int] = set()
    for token in tokens:
        for key, idxs in _candidate_map.items():
            if token in key or key in token:
                candidate_idx.update(idxs)

    if not candidate_idx:
        return product_df  # fallback: search all

    return product_df.loc[list(candidate_idx)]


def _invalidate_candidate_map() -> None:
    global _candidate_map
    _candidate_map = None


# ── core matching ─────────────────────────────────────────────────────────────
def search(query: str, max_results: int = 50) -> list[MatchResult]:
    """
    Search for products matching the given query.
    Returns list of MatchResult sorted by score desc.
    """
    drug_df, product_df = load_data()
    query = query.strip()
    if not query:
        return []

    q_norm = normalize(query)
    results: list[MatchResult] = []
    seen_brands: set[str] = set()

    def _add(row: pd.Series, match_type: str, score: int) -> None:
        key = str(row.get("brand", "")).strip()
        if not key or key in seen_brands:
            return
        seen_brands.add(key)
        results.append(
            MatchResult(
                query=query,
                brand=row.get("brand", ""),
                molecules=row.get("molecules", ""),
                strength=row.get("strength", ""),
                dosage_form=row.get("dosage_form", ""),
                match_type=match_type,
                score=score,
                sheet=row.get("sheet", ""),
                composition=row.get("composition", ""),
            )
        )

    # ── 1. Exact match ────────────────────────────────────────────────────────
    mask_exact = (
        (product_df["norm_molecules"] == q_norm)
        | (product_df["norm_brand"] == q_norm)
        | product_df["norm_composition"].apply(lambda x: q_norm in x.split())
    )
    for _, row in product_df[mask_exact].iterrows():
        _add(row, "exact", 100)

    # ── 2. Partial (substring) match ──────────────────────────────────────────
    candidates = _get_candidate_rows(q_norm, product_df)
    mask_partial = (
        candidates["norm_molecules"].str.contains(q_norm, regex=False, na=False)
        | candidates["norm_composition"].str.contains(q_norm, regex=False, na=False)
        | candidates["norm_brand"].str.contains(q_norm, regex=False, na=False)
    )
    for _, row in candidates[mask_partial].iterrows():
        _add(row, "partial", 90)

    # Also check if query contains the molecule name (reverse partial)
    mask_rev = candidates["norm_molecules"].apply(
        lambda m: bool(m) and m in q_norm
    )
    for _, row in candidates[mask_rev].iterrows():
        _add(row, "partial", 85)

    # ── 3. Fuzzy match ────────────────────────────────────────────────────────
    if len(results) < max_results:
        # Build unique search strings from molecules + brand
        search_strings = (
            candidates["norm_molecules"].fillna("") + " "
            + candidates["norm_brand"].fillna("")
        ).str.strip()

        scored = process.extract(
            q_norm,
            search_strings.tolist(),
            scorer=fuzz.WRatio,
            limit=max_results * 2,
            score_cutoff=FUZZY_THRESHOLD,
        )

        for _text, score, idx in scored:
            real_idx = candidates.index[idx]
            row = candidates.loc[real_idx]
            _add(row, "fuzzy", int(score))

    # ── Sort & limit ──────────────────────────────────────────────────────────
    results.sort(key=lambda r: (-r.score, r.brand))
    return results[:max_results]


def batch_search(queries: list[str], max_per_query: int = 20) -> list[dict]:
    """Run search() for each query, tag each result with its source query."""
    out = []
    for q in queries:
        q = q.strip()
        if not q:
            continue
        hits = search(q, max_per_query)
        if hits:
            for h in hits:
                out.append(h.to_dict())
        else:
            out.append({
                "query":       q,
                "brand":       "",
                "molecules":   "",
                "strength":    "",
                "dosage_form": "",
                "match_type":  "no match",
                "score":       0,
                "sheet":       "",
            })
    return out


def invalidate_cache() -> None:
    """Call after reload_data() to clear the candidate index."""
    _invalidate_candidate_map()
