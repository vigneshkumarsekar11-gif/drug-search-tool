"""
matcher.py — Fuzzy / partial / exact matching (pandas-free, works on Vercel).

Priority:
  1. Exact   — norm query == norm molecule/brand
  2. Partial — query is a substring of molecule/brand or vice-versa
  3. Fuzzy   — rapidfuzz WRatio >= FUZZY_THRESHOLD
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from data_loader import load_data, normalize

FUZZY_THRESHOLD = 70


@dataclass
class MatchResult:
    query:       str
    brand:       str
    molecules:   str
    strength:    str
    dosage_form: str
    match_type:  str   # exact | partial | fuzzy
    score:       int   # 100 = exact
    sheet:       str = ""
    composition: str = ""

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


# ── Candidate index (built once, cached in memory) ────────────────────────────
_candidate_map: dict[str, list[int]] | None = None


def _build_index(products: list[dict]) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = {}
    for i, p in enumerate(products):
        key = (p.get("norm_molecules", "") + " " + p.get("norm_composition", "")).strip()
        for token in key.split():
            if len(token) >= 3:
                idx.setdefault(token, []).append(i)
    return idx


def _candidates(q_norm: str, products: list[dict]) -> list[dict]:
    global _candidate_map
    if _candidate_map is None:
        _candidate_map = _build_index(products)

    tokens = [t for t in q_norm.split() if len(t) >= 3]
    if not tokens:
        return products

    idxs: set[int] = set()
    for token in tokens:
        for key, rows in _candidate_map.items():
            if token in key or key in token:
                idxs.update(rows)

    return [products[i] for i in idxs] if idxs else products


def invalidate_cache() -> None:
    global _candidate_map
    _candidate_map = None


# ── Core search ───────────────────────────────────────────────────────────────
def search(query: str, max_results: int = 50) -> list[MatchResult]:
    _, products = load_data()
    query = query.strip()
    if not query:
        return []

    q_norm = normalize(query)
    results: list[MatchResult] = []
    seen: set[str] = set()

    def add(p: dict, match_type: str, score: int) -> None:
        brand = p.get("brand", "").strip()
        if not brand or brand in seen:
            return
        seen.add(brand)
        results.append(MatchResult(
            query=query, brand=brand,
            molecules=p.get("molecules", ""),
            strength=p.get("strength", ""),
            dosage_form=p.get("dosage_form", ""),
            match_type=match_type, score=score,
            sheet=p.get("sheet", ""),
            composition=p.get("composition", ""),
        ))

    # 1. Exact
    for p in products:
        nm = p.get("norm_molecules", "")
        nb = p.get("norm_brand", "")
        nc = p.get("norm_composition", "")
        if q_norm in (nm, nb) or q_norm in nc.split():
            add(p, "exact", 100)

    # 2. Partial (substring)
    cands = _candidates(q_norm, products)
    for p in cands:
        nm = p.get("norm_molecules", "")
        nb = p.get("norm_brand", "")
        nc = p.get("norm_composition", "")
        if (q_norm in nm or q_norm in nb or q_norm in nc
                or (nm and nm in q_norm)):
            add(p, "partial", 90)

    # 3. Fuzzy
    if len(results) < max_results:
        search_strings = [
            (p.get("norm_molecules", "") + " " + p.get("norm_brand", "")).strip()
            for p in cands
        ]
        scored = process.extract(
            q_norm, search_strings,
            scorer=fuzz.WRatio,
            limit=max_results * 2,
            score_cutoff=FUZZY_THRESHOLD,
        )
        for _text, score, idx in scored:
            add(cands[idx], "fuzzy", int(score))

    results.sort(key=lambda r: (-r.score, r.brand))
    return results[:max_results]


def batch_search(queries: list[str], max_per_query: int = 20) -> list[dict]:
    out = []
    for q in queries:
        q = q.strip()
        if not q:
            continue
        hits = search(q, max_per_query)
        if hits:
            out.extend(h.to_dict() for h in hits)
        else:
            out.append({
                "query": q, "brand": "", "molecules": "",
                "strength": "", "dosage_form": "",
                "match_type": "no match", "score": 0, "sheet": "",
            })
    return out
