"""Northwind Cycles support bot — HTTP server.

Run:  python app.py          then open http://127.0.0.1:5000
API:  POST /api/chat  {"message": "...", "session_id": "..."}
"""

import os
import uuid

from flask import Flask, jsonify, request, render_template, send_from_directory

from chatbot import ChatbotEngine
from chatbot import analytics
from chatbot import grok

app = Flask(__name__)
engine = ChatbotEngine("data/intents.json")

# Sessions live in memory, which is fine for one process. Behind gunicorn
# with several workers, swap this for Redis so a user keeps their context.
SESSIONS = {}

# Domains allowed to embed the widget. "*" is convenient while developing;
# list your real origins before going live.
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")


@app.after_request
def cors(response):
    """Let the widget call this API from the customer's own domain."""
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGINS
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/")
def home():
    """Demo storefront with the widget already installed."""
    return render_template("index.html", business=engine.business)


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return ("", 204)

    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    session_id = payload.get("session_id") or str(uuid.uuid4())

    if len(message) > 500:
        message = message[:500]

    context = SESSIONS.setdefault(session_id, {})
    reply = engine.respond(message, context)

    # Retrieval answers everything it was trained on — that's policy, and it
    # stays exact. Grok only ever sees the leftovers: questions the training
    # data doesn't cover. This order means a wrong policy answer can never
    # come from the generative side.
    if reply.is_fallback and grok.enabled():
        generated = grok.ask(message, engine.business)
        if generated:
            reply.text = generated
            reply.intent = "grok_generated"

    analytics.log_turn(session_id, message, reply)

    body = reply.to_dict()
    body["session_id"] = session_id
    return jsonify(body)


@app.route("/api/feedback", methods=["POST", "OPTIONS"])
def feedback():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    analytics.log_feedback(
        payload.get("session_id", "unknown"),
        payload.get("helpful", False),
        payload.get("note", ""),
    )
    return jsonify({"recorded": True})


@app.route("/api/metrics")
def metrics():
    """Engagement dashboard data. Put this behind auth in production."""
    return jsonify({
        "model": engine.stats,
        "engagement": analytics.metrics(),
        "grok_enabled": grok.enabled(),
    })


@app.route("/api/reload", methods=["POST"])
def reload_intents():
    """Retrain from intents.json without dropping the server."""
    return jsonify(engine.reload())


@app.route("/widget.js")
def widget_js():
    """Single-line install target: <script src=".../widget.js"></script>"""
    return send_from_directory("static", "widget.js", mimetype="application/javascript")


if __name__ == "__main__":
    print(f"Loaded {engine.stats['intents']} intents, "
          f"{engine.stats['patterns']} patterns, "
          f"{engine.stats['features']} features")
    print(f"Grok fallback: {'ON (' + grok.GROK_MODEL + ')' if grok.enabled() else 'OFF (set GROK_API_KEY to enable)'}")
    app.run(host="127.0.0.1", port=5000, debug=True)
