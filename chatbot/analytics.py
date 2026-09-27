"""Conversation logging and engagement metrics.

Every turn is appended to logs/conversations.jsonl. That file is the raw
material for two things: the live metrics on /api/metrics, and the list of
unmatched questions you paste back into intents.json to retrain.
"""

import json
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path("logs/conversations.jsonl")
_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_turn(session_id, message, reply):
    LOG_PATH.parent.mkdir(exist_ok=True)
    record = {
        "ts": _now(),
        "session": session_id,
        "message": message,
        "intent": reply.intent,
        "confidence": round(float(reply.confidence), 3),
        "fallback": reply.is_fallback,
        "escalated": reply.escalate,
    }
    with _lock:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")


def log_feedback(session_id, helpful, note=""):
    LOG_PATH.parent.mkdir(exist_ok=True)
    record = {
        "ts": _now(),
        "session": session_id,
        "type": "feedback",
        "helpful": bool(helpful),
        "note": note,
    }
    with _lock:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")


def _read():
    if not LOG_PATH.exists():
        return []
    rows = []
    with open(LOG_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def metrics():
    """Engagement summary used by /api/metrics and the demo dashboard."""
    rows = _read()
    turns = [r for r in rows if r.get("type") != "feedback"]
    votes = [r for r in rows if r.get("type") == "feedback"]

    if not turns:
        return {
            "sessions": 0, "turns": 0, "turns_per_session": 0,
            "fallback_rate": 0, "containment_rate": 0,
            "avg_confidence": 0, "helpful_rate": None,
            "top_intents": [], "unmatched": [],
        }

    sessions = {r["session"] for r in turns}
    escalated = {r["session"] for r in turns if r.get("escalated")}
    fallbacks = [r for r in turns if r.get("fallback")]
    helpful = [v for v in votes if v["helpful"]]

    return {
        "sessions": len(sessions),
        "turns": len(turns),
        "turns_per_session": round(len(turns) / len(sessions), 2),
        # share of turns the bot could not match at all
        "fallback_rate": round(len(fallbacks) / len(turns), 3),
        # share of sessions resolved without handing off to staff
        "containment_rate": round(1 - len(escalated) / len(sessions), 3),
        "avg_confidence": round(
            sum(r["confidence"] for r in turns) / len(turns), 3
        ),
        "helpful_rate": round(len(helpful) / len(votes), 3) if votes else None,
        "top_intents": Counter(
            r["intent"] for r in turns if r["intent"] != "fallback"
        ).most_common(8),
        # retraining queue: real questions the bot missed
        "unmatched": [r["message"] for r in fallbacks][-25:],
    }
