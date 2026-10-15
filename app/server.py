"""Serves the dashboard. Local: python app/server.py (127.0.0.1:8080). Cloud Run: gunicorn, see Dockerfile.

Static files plus three guarded endpoints: /api/ask (app/ask_gemini.py, OFF unless ASK_GEMINI_ENABLED=1), /api/factcheck
(app/factcheck.py, ON locally, OFF on a platform that sets PORT unless FACTCHECK_ENABLED=1) and /api/brief-ai (app/brief_ai.py, OFF
everywhere unless BRIEF_AI_ENABLED=1), all with caches, rate limits and a daily cap (docs/ask-endpoint.md, docs/factcheck-endpoint.md,
docs/brief-ai-endpoint.md). Nothing else here may call Gemini or any external service.
"""
import logging
import os

from flask import Flask, send_from_directory

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")   # the endpoints log reason codes at INFO; Cloud Run shows stderr
app = Flask(__name__, static_folder="static", static_url_path="")
try:
    import ask_gemini
    ask_gemini.register(app)
except ImportError:      # image built without app/ask_gemini.py: serve the dashboard without the Ask endpoint
    @app.get("/api/ask/status")
    def ask_status_off():      # the page probes this; answer "off" instead of a 404 in the console
        return {"enabled": False}
try:
    import factcheck
    factcheck.register(app)
except ImportError:      # image built without app/factcheck.py: no fact-check button backend
    pass
try:
    import brief_ai
    brief_ai.register(app)
except ImportError:      # image built without app/brief_ai.py: no Brief rewrite backend
    @app.get("/api/brief-ai/status")
    def brief_status_off():
        return {"enabled": False}

# Scripts, fetches and images: same origin only. style-src needs 'unsafe-inline' because app.js sets SVG style attributes.
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.after_request
def headers(resp):
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000"   # browsers ignore it over plain http (local runs)
    # results.json changes whenever the pipeline reruns; never serve a stale copy.
    if resp.mimetype == "application/json":
        resp.headers["Cache-Control"] = "no-store"
    elif resp.mimetype in ("text/html", "text/css", "text/javascript", "application/javascript"):
        resp.headers["Cache-Control"] = "no-cache"   # revalidate every time, so edits show on a normal reload
    return resp


if __name__ == "__main__":
    port = os.environ.get("PORT")
    # Bind all interfaces only when a platform sets PORT (Cloud Run, containers); local runs stay on loopback.
    app.run(host="0.0.0.0" if port else "127.0.0.1", port=int(port or 8080))
