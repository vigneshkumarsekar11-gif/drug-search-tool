import io
import logging

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file

from data_handler import DataHandler
from search import PharmSearch

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

data_handler = DataHandler("data/products.csv")
searcher = PharmSearch(data_handler)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search", methods=["POST"])
def search():
    body = request.get_json(silent=True) or {}
    raw_query = body.get("query", "").strip()
    if not raw_query:
        return jsonify({"error": "Query cannot be empty."}), 400

    # Support comma-separated multi-query from the text bar
    queries = [q.strip() for q in raw_query.split(",") if q.strip()]
    results = searcher.search_multiple(queries)

    total_hits = sum(len(r["results"]) for r in results)
    logger.info("TEXT SEARCH | queries=%d total_hits=%d | %s", len(queries), total_hits, raw_query[:120])
    return jsonify({"results": results})


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    try:
        queries = data_handler.parse_upload(file)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        logger.error("Upload parse error: %s", exc)
        return jsonify({"error": "Could not parse the uploaded file."}), 400

    results = searcher.search_multiple(queries)
    total_hits = sum(len(r["results"]) for r in results)
    logger.info("FILE UPLOAD  | file=%s queries=%d total_hits=%d", file.filename, len(queries), total_hits)
    return jsonify({"results": results, "queries_count": len(queries)})


@app.route("/api/download", methods=["POST"])
def download():
    body = request.get_json(silent=True) or {}
    results = body.get("results", [])

    rows = []
    for item in results:
        query = item.get("query", "")
        matches = item.get("results", [])
        if matches:
            for r in matches:
                rows.append({
                    "Input Query": query,
                    "Product Name": r.get("product_name", ""),
                    "Generic Name": r.get("generic_name", ""),
                    "Molecule Name": r.get("molecule_name", ""),
                    "Composition": r.get("composition", ""),
                    "Strength": r.get("strength", ""),
                    "Dosage Form": r.get("dosage_form", ""),
                    "Company Name": r.get("company_name", ""),
                    "Match Score (%)": r.get("score", ""),
                    "Matched Field": r.get("matched_field", ""),
                })
        else:
            rows.append({
                "Input Query": query,
                "Product Name": "No match found",
                "Generic Name": "", "Molecule Name": "", "Composition": "",
                "Strength": "", "Dosage Form": "", "Company Name": "",
                "Match Score (%)": "", "Matched Field": "",
            })

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    logger.info("DOWNLOAD | %d rows exported", len(rows))
    return send_file(
        buf,
        mimetype="text/csv",
        as_attachment=True,
        download_name="pharma_search_results.csv",
    )


@app.route("/api/autocomplete")
def autocomplete():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    return jsonify(searcher.get_suggestions(q))


@app.route("/api/reload", methods=["POST"])
def reload_data():
    try:
        data_handler.reload()
        return jsonify({"message": "Dataset reloaded.", "product_count": len(data_handler.df)})
    except Exception as exc:
        logger.error("Reload error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
