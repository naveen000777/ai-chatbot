"""Text normalisation for the retrieval engine.

Kept dependency-free on purpose: no NLTK download step, so the project
runs offline straight after `pip install -r requirements.txt`.
"""

import re

CONTRACTIONS = {
    "what's": "what is", "whats": "what is", "where's": "where is",
    "wheres": "where is", "how's": "how is", "hows": "how is",
    "i'm": "i am", "im": "i am", "i've": "i have", "ive": "i have",
    "don't": "do not", "dont": "do not", "can't": "can not",
    "cant": "can not", "won't": "will not", "wont": "will not",
    "it's": "it is", "its": "it is", "doesn't": "does not",
    "doesnt": "does not", "haven't": "have not", "havent": "have not",
    "isn't": "is not", "isnt": "is not", "didn't": "did not",
    "didnt": "did not", "you're": "you are", "youre": "you are",
    "i'd": "i would", "id like": "i would like", "let's": "let us",
    "there's": "there is", "theres": "there is", "that's": "that is",
    "thats": "that is", "wasn't": "was not", "couldn't": "could not",
    "shouldn't": "should not", "hasn't": "has not",
}

# Domain vocabulary folded onto a canonical term so that customer wording
# and training patterns meet in the middle.
SYNONYMS = {
    "parcel": "order", "package": "order", "shipment": "order",
    "purchase": "order", "delivery": "shipping", "deliver": "ship",
    "postage": "shipping", "refund": "return", "reimbursement": "return",
    "money back": "refund return", "guarantee": "warranty",
    "faulty": "broken defective", "damaged": "broken",
    "cycle": "bike", "bicycle": "bike", "ebike": "bike",
    "repair": "service", "fix": "service", "tune up": "service",
    "servicing": "service", "maintenance": "service",
    "measurement": "size", "sizing": "size", "fit": "size",
    "coupon": "discount", "voucher": "discount", "promo": "discount",
    "offer": "discount", "deal": "discount", "sale": "discount",
    "rep": "agent", "human": "agent", "person": "agent",
    "staff": "agent", "representative": "agent", "support": "agent",
    "cost": "price", "charge": "price", "fee": "price",
    "available": "stock", "availability": "stock",
    "store": "shop", "opening": "hours", "timings": "hours",
    "chat bot": "bot", "chatbot": "bot",
}

_PUNCT = re.compile(r"[^\w\s£$€]")
_SPACE = re.compile(r"\s+")

# e.g. NW-12345, nw12345, #NW 12345
ORDER_ID = re.compile(r"\b(?:nw[\s\-#]?)?(\d{4,8})\b", re.I)


def normalize(text: str) -> str:
    """Lowercase, expand contractions, fold synonyms, strip punctuation."""
    text = text.lower().strip()
    for short, long in CONTRACTIONS.items():
        text = text.replace(short, long)
    text = _PUNCT.sub(" ", text)
    text = _SPACE.sub(" ", text).strip()

    words = text.split()
    expanded = []
    for word in words:
        expanded.append(SYNONYMS.get(word, word))
    text = " ".join(expanded)

    for phrase, canonical in SYNONYMS.items():
        if " " in phrase and phrase in text:
            text = text.replace(phrase, canonical)
    return _SPACE.sub(" ", text).strip()


def extract_order_id(text: str):
    """Pull an order number out of free text, returned in NW-00000 form."""
    match = ORDER_ID.search(text)
    if not match:
        return None
    return f"NW-{match.group(1)}"
