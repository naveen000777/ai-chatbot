"""Generative fallback via xAI's Grok API.

Design: the retrieval engine stays the primary responder for every intent it
knows, because those replies are policy the business signed off on. Grok is
called ONLY when the retrieval engine gives up (fallback), so a wrong guess
about, say, the return window can never come from the generative side — it
just answers the free-form questions the training data never covered.

If GROK_API_KEY is not set, calls are skipped and the engine's normal
fallback message is used instead — the bot still works with zero config.
"""

import os

import requests

GROK_API_KEY = os.environ.get("GROK_API_KEY", "").strip()
GROK_MODEL = os.environ.get("GROK_MODEL", "grok-4")
GROK_URL = "https://api.x.ai/v1/chat/completions"
TIMEOUT_SECONDS = 12

SYSTEM_PROMPT = (
    "You are a support assistant for {business}, a {domain} business. "
    "Answer in 2-3 short sentences, plain and friendly, no markdown. "
    "You do not have access to the customer's order, account or live stock, "
    "so never invent order numbers, prices, dates or policy details you are "
    "not given. If the question needs any of that, say a staff member can "
    "help and point them to {email}. Stay strictly on topics a bike shop's "
    "customer service would cover; if the question is unrelated to the "
    "business, say so briefly and offer to help with something the shop "
    "does handle."
)


def enabled() -> bool:
    return bool(GROK_API_KEY)


def ask(message: str, business: dict) -> str | None:
    """Return a Grok-generated reply, or None if the call fails or is unset.

    None on failure (not an exception) so the caller can fall back to the
    engine's own canned message without extra error handling at the call site.
    """
    if not enabled() or not message:
        return None

    system = SYSTEM_PROMPT.format(
        business=business.get("name", "the shop"),
        domain=business.get("domain", "retail"),
        email=business.get("support_email", "our support team"),
    )

    try:
        response = requests.post(
            GROK_URL,
            headers={
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROK_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
                "temperature": 0.4,
                "max_tokens": 200,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()
        return text or None
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        # A live support bot must degrade quietly. Print for the developer's
        # terminal; the customer just sees the ordinary fallback message.
        print(f"[grok] call failed, using canned fallback instead: {exc}")
        return None
