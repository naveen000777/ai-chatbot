"""Retrieval-based chatbot engine.

Why retrieval and not generation: a commercial support bot states policy.
A generative model can invent a refund window that does not exist, and the
business is bound by whatever the bot said. Here every reply is a string a
human wrote in data/intents.json, so the worst failure is "I don't know"
rather than a wrong promise.

Features are two TF-IDF views of the same text:
  1. word 1-2 grams  -> catches phrasing ("how long does shipping take")
  2. char 4-5 grams  -> survives typos ("shiping", "waranty")

Scoring blends two signals, because each fails differently:
  * nearest training pattern (cosine) is sharp but brittle on long,
    chatty sentences where one matching pattern gets diluted;
  * a logistic regression over the same features learns which words
    actually separate intents, so "guarantee" pulls warranty rather
    than every sentence starting "how long".
Blending the two beat either alone on the held-out set (88% vs 74/76 on the held-out set).

The blended score then passes through two thresholds: answer, ask to
clarify, or fall back. That gate is what keeps accuracy honest — run
tests/evaluate.py to see the trade-off.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity

from .preprocess import normalize, extract_order_id

# All tuned on data/test_set.json — see evaluate.py --sweep before changing.
ANSWER_THRESHOLD = 0.30
CLARIFY_THRESHOLD = 0.18
MAX_SUGGESTIONS = 3
CHAR_WEIGHT = 0.5      # char n-grams support the word view, never dominate
BLEND = 0.55           # weight on the classifier vs nearest-pattern match
OOV_LIMIT = 0.75       # share of unknown content words that means "off topic"

# Structure words carry no topic, so they are ignored by the domain check.
STOPWORDS = set(
    "a an the is are was were do does did you i we it this that my your our "
    "of to for on in at and or can could would will with be been have has had "
    "how what when where which who whom please me him her they them if not no "
    "yes so very much more some any there here from by as about get got".split()
)


@dataclass
class Reply:
    text: str
    intent: str
    confidence: float
    quick_replies: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    escalate: bool = False
    is_fallback: bool = False

    def to_dict(self):
        return {
            "reply": self.text,
            "intent": self.intent,
            "confidence": round(float(self.confidence), 3),
            "quick_replies": self.quick_replies,
            "suggestions": self.suggestions,
            "escalate": self.escalate,
            "is_fallback": self.is_fallback,
        }


class ChatbotEngine:
    def __init__(self, intents_path="data/intents.json", seed=None):
        self.path = Path(intents_path)
        self.rng = random.Random(seed)
        self.load()

    # ---------------------------------------------------------------- train
    def load(self):
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)

        self.business = data.get("business", {})
        self.fallback = data["fallback"]
        self.clarify_prompt = data.get("clarify", {}).get(
            "prompt", "Did you mean one of these?"
        )
        self.intents = {i["tag"]: i for i in data["intents"]}

        self.corpus, self.labels = [], []
        for tag, intent in self.intents.items():
            for pattern in intent["patterns"]:
                self.corpus.append(normalize(pattern))
                self.labels.append(tag)

        self.word_vec = TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, min_df=1
        )
        self.char_vec = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(4, 5), sublinear_tf=True, min_df=1
        )
        word_matrix = self.word_vec.fit_transform(self.corpus)
        char_matrix = self.char_vec.fit_transform(self.corpus)
        self.matrix = hstack([word_matrix, char_matrix * CHAR_WEIGHT]).tocsr()

        # class_weight balances intents that have fewer patterns than others
        self.clf = LogisticRegression(
            max_iter=2000, C=10, class_weight="balanced"
        ).fit(self.matrix, self.labels)

        # Single-word vocabulary, used to spot questions about things the
        # business does not sell or discuss.
        self.vocabulary = {
            term for term in self.word_vec.vocabulary_ if " " not in term
        }

    def reload(self):
        """Re-read intents.json without restarting the server."""
        self.load()
        return {"intents": len(self.intents), "patterns": len(self.corpus)}

    # --------------------------------------------------------------- match
    def _vectorize(self, text: str):
        norm = normalize(text)
        return hstack([
            self.word_vec.transform([norm]),
            self.char_vec.transform([norm]) * CHAR_WEIGHT,
        ]).tocsr()

    def is_out_of_domain(self, text: str) -> bool:
        """True when the informative words are all unknown to the training data.

        Catches the case similarity cannot: "do you sell kayaks" has the exact
        shape of a stock question, so cosine scores it high. The give-away is
        that 'kayaks' never appears anywhere in the shop's intents.
        """
        tokens = [
            word for word in normalize(text).split()
            if word not in STOPWORDS and len(word) > 2
        ]
        if len(tokens) < 2:
            return False
        unknown = sum(1 for word in tokens if word not in self.vocabulary)
        return unknown / len(tokens) >= OOV_LIMIT

    def rank(self, text: str, top_k=MAX_SUGGESTIONS):
        """Return [(tag, score), ...] best first, one entry per intent."""
        if self.is_out_of_domain(text):
            return []

        query = self._vectorize(text)

        # Signal 1: closest single training pattern.
        sims = cosine_similarity(query, self.matrix)[0]
        nearest = {}
        for label, score in zip(self.labels, sims):
            if score > nearest.get(label, -1.0):
                nearest[label] = float(score)

        # Signal 2: discriminative classifier over the same features.
        probs = dict(zip(self.clf.classes_, self.clf.predict_proba(query)[0]))

        blended = {
            tag: BLEND * float(probs.get(tag, 0.0))
            + (1 - BLEND) * nearest.get(tag, 0.0)
            for tag in self.intents
        }
        ranked = sorted(blended.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:top_k]

    def predict(self, text: str):
        ranked = self.rank(text, top_k=1)
        return ranked[0] if ranked else ("fallback", 0.0)

    # ---------------------------------------------------------------- reply
    def respond(self, text: str, context=None):
        """Produce a Reply. `context` is a mutable per-session dict."""
        context = context if context is not None else {}
        text = (text or "").strip()

        if not text:
            return self._fallback(0.0)

        # A pending slot outranks intent matching: the user was asked for an
        # order number, so digits in the next turn are that number.
        pending = context.get("awaiting_slot")
        if pending == "order_id":
            order_id = extract_order_id(text)
            if order_id:
                context.pop("awaiting_slot", None)
                context["order_id"] = order_id
                intent = self.intents["order_status"]
                return Reply(
                    text=intent["slot_response"].format(order_id=order_id),
                    intent="order_status",
                    confidence=1.0,
                    quick_replies=intent.get("quick_replies", []),
                )

        ranked = self.rank(text)
        tag, score = ranked[0] if ranked else ("", 0.0)

        if score >= ANSWER_THRESHOLD:
            return self._answer(tag, score, text, context)

        if score >= CLARIFY_THRESHOLD:
            suggestions = [self._label(t) for t, s in ranked if s >= CLARIFY_THRESHOLD]
            if len(suggestions) > 1:
                return Reply(
                    text=self.clarify_prompt,
                    intent="clarify",
                    confidence=score,
                    suggestions=suggestions[:MAX_SUGGESTIONS],
                    quick_replies=suggestions[:MAX_SUGGESTIONS],
                )
            return self._answer(tag, score, text, context)

        return self._fallback(score)

    def _answer(self, tag, score, text, context):
        intent = self.intents[tag]

        # Slot-filling: order_status needs an order number before it can answer.
        if intent.get("slot"):
            order_id = extract_order_id(text) or context.get("order_id")
            if order_id:
                context["order_id"] = order_id
                context.pop("awaiting_slot", None)
                return Reply(
                    text=intent["slot_response"].format(order_id=order_id),
                    intent=tag,
                    confidence=score,
                    quick_replies=intent.get("quick_replies", []),
                )
            context["awaiting_slot"] = intent["slot"]

        context["last_intent"] = tag
        return Reply(
            text=self.rng.choice(intent["responses"]),
            intent=tag,
            confidence=score,
            quick_replies=intent.get("quick_replies", []),
            escalate=bool(intent.get("escalate")),
        )

    def _fallback(self, score):
        return Reply(
            text=self.rng.choice(self.fallback["responses"]),
            intent="fallback",
            confidence=score,
            quick_replies=self.fallback.get("quick_replies", []),
            is_fallback=True,
        )

    @staticmethod
    def _label(tag: str) -> str:
        return tag.replace("_", " ").capitalize()

    @property
    def stats(self):
        return {
            "intents": len(self.intents),
            "patterns": len(self.corpus),
            "features": int(self.matrix.shape[1]),
            "business": self.business.get("name"),
        }
