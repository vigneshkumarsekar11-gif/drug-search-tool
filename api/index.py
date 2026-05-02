"""
api/index.py — Vercel serverless entry point.
Adds the project root to sys.path, then imports the Flask app.
"""
import sys
import os

# Make sure the project root is importable
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

from web import app   # noqa: E402  (import after path manipulation)

# Vercel looks for a variable named `app` or `handler`
handler = app
