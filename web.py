"""
web.py — Flask application entry point for the Pharma Product Search tool.

Routes:
  GET  /                  → main search page
  POST /search            → single-query search (JSON)
  POST /batch             → batch file upload search (JSON)
  GET  /autocomplete      → autocomplete suggestions (JSON)
  GET  /download          → download last batch/search results as Excel
  POST /reload            → force reload source data files
"""

import io
import json
import logging
import os
import tempfile

import pandas as pd
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
    session,
)

from data_loader import load_data, reload, get_all_generic_names, get_all_molecule_names
from matcher import search, batch_search, invalidate_cache

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pharma-search-dev-key-change-in-prod")

# Max upload size 20 MB
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

# Never cache static files or HTML — prevents stale JS/CSS in the browser
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Warm up data on startup
logger.info("Pre-loading datasets...")
try:
    load_data()
    logger.info("Datasets ready.")
except Exception as exc:
    logger.error("Failed to pre-load datasets: %s", exc)

# In-memory result store for download (simple; stateless in prod → use temp files)
_last_results: list[dict] = []


# ── routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search_route():
    body = request.get_json(silent=True) or {}
    query = (body.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Empty query"}), 400

    results = search(query, max_results=50)
    data = [r.to_dict() for r in results]

    global _last_results
    _last_results = data

    return jsonify({"query": query, "count": len(data), "results": data})


@app.route("/batch", methods=["POST"])
def batch_route():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = file.filename.lower()
    try:
        if filename.endswith(".csv") or filename.endswith(".txt"):
            content = file.read().decode("utf-8", errors="replace")
            lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            # Support comma or newline separated
            if len(lines) == 1 and "," in lines[0]:
                queries = [q.strip() for q in lines[0].split(",") if q.strip()]
            else:
                queries = lines
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(file, header=None, dtype=str)
            # Use first column
            queries = df.iloc[:, 0].dropna().str.strip().tolist()
        else:
            return jsonify({"error": "Unsupported file type. Use CSV, TXT, or XLSX."}), 400
    except Exception as exc:
        logger.exception("Batch file parse error")
        return jsonify({"error": f"Could not parse file: {exc}"}), 400

    if not queries:
        return jsonify({"error": "No queries found in file"}), 400

    results = batch_search(queries, max_per_query=20)

    global _last_results
    _last_results = results

    return jsonify({"count": len(results), "queries": len(queries), "results": results})


@app.route("/autocomplete")
def autocomplete():
    q = (request.args.get("q") or "").strip().lower()
    if len(q) < 2:
        return jsonify([])

    generics  = get_all_generic_names()
    molecules = get_all_molecule_names()
    combined  = sorted(set(generics + molecules))

    matches = [name for name in combined if q in name.lower()][:20]
    return jsonify(matches)


@app.route("/download")
def download():
    if not _last_results:
        return jsonify({"error": "No results to download yet"}), 400

    df = pd.DataFrame(_last_results)
    # Rename for user-friendly headers
    df = df.rename(columns={
        "query":       "Input Query",
        "brand":       "Product (Brand) Name",
        "molecules":   "Molecules",
        "strength":    "Strength",
        "dosage_form": "Dosage Form",
        "match_type":  "Match Type",
        "score":       "Confidence Score",
        "sheet":       "Source Sheet",
    })

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Search Results")
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="pharma_search_results.xlsx",
    )


@app.route("/reload", methods=["POST"])
def reload_data():
    try:
        drug_df, product_df = reload()
        invalidate_cache()
        return jsonify({
            "status": "ok",
            "drug_entries":    len(drug_df),
            "product_entries": len(product_df),
        })
    except Exception as exc:
        logger.exception("Reload failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/stats")
def stats():
    drug_df, product_df = load_data()
    return jsonify({
        "drug_entries":    len(drug_df),
        "product_entries": len(product_df),
    })


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # threaded=True allows concurrent requests (default dev server is single-threaded)
    app.run(debug=False, port=5000, use_reloader=False, threaded=True)
