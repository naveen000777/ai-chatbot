# Northwind Cycles Support Bot

A retrieval-based chatbot that answers customer questions on a website, trained
on predefined input patterns and embeddable with one script tag. Two upgrades
on top of the base build: the widget opens **full screen** instead of a corner
box, and unanswered questions get a **Grok-generated reply** instead of a flat
"I don't know" — while every policy answer (returns, shipping, warranty) still
comes only from the trained data, never from Grok.

Measured on a held-out test set: **96% intent accuracy, 100% of off-topic
questions correctly refused.**

---

## Run it in VS Code

```bash
# 1. open the folder in VS Code:  File > Open Folder > ai-chatbot
# 2. create an environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS / Linux

# 3. install
pip install -r requirements.txt

# 4. run
python app.py
```

Open <http://127.0.0.1:5000> and click **Ask us** in the bottom right.

Press `F5` instead of step 4 to use the debugger. Four launch configurations are
preset: run the server, check accuracy, sweep thresholds, test typo robustness.

If `python` is not found, press `Ctrl+Shift+P` → *Python: Select Interpreter* →
pick the one inside `venv`.

---

## Why retrieval and not a generative model

A support bot states policy. If it generates text freely it can invent a refund
window the business then has to honour. Here every reply is a sentence a human
wrote in `data/intents.json`, so the worst failure is "I don't know" rather than
a wrong promise. It also runs on CPU, needs no API key, and retrains in under a
second when a policy changes.

A generative model is the better choice when answers must be composed from a
long document per query. That is a different system, usually retrieval plus
generation, and it needs a review process this one does not.

---

## How a message becomes an answer

```
"how long does shiping take"
   │
   ├─ normalize      lowercase, expand "what's"→"what is", fold
   │                 "postage"→"shipping", strip punctuation
   │
   ├─ vectorize      word 1-2 grams  → phrasing
   │                 char 4-5 grams  → survives the typo in "shiping"
   │
   ├─ score          blend of two signals:
   │                   0.55 × logistic regression over those features
   │                   0.45 × cosine to the nearest training pattern
   │
   ├─ domain check   are the informative words known to the shop at all?
   │
   └─ confidence gate
         ≥ 0.30  answer
         ≥ 0.18  "did you mean one of these?" + top 3
         below   fallback, offer a human
```

**Why blend two scorers.** Nearest-pattern cosine is sharp but brittle: in a long
chatty sentence the one matching pattern gets diluted. Logistic regression learns
which words actually separate intents, so "guarantee" pulls *warranty* instead of
every sentence starting "how long". Alone they scored 74% and 76%; blended, 88%.

**Why the domain check exists.** "do you sell kayaks" has the exact shape of a
real stock question, so similarity rates it 0.52 — high enough to answer. The
give-away is that *kayaks* appears nowhere in the training data. So if 75% or
more of the informative words are unknown, the bot refuses regardless of score.
That single rule took off-topic rejection from 60% to 100%.

---

## Grok fallback (optional)

Retrieval answers everything it was trained on — that stays exact policy.
When it can't match anything at all, it can hand off to Grok instead of a flat
"I don't know", for the free-form questions no training set fully covers.

**Get a key** from <https://console.x.ai>, then set it before running:

```powershell
# PowerShell, current session only
$env:GROK_API_KEY = "xai-your-key-here"
python app.py
```

```bash
# macOS / Linux
export GROK_API_KEY="xai-your-key-here"
python app.py
```

Startup log confirms which mode is active:

```
Grok fallback: ON (grok-4)          # key found
Grok fallback: OFF (set GROK_API_KEY to enable)   # no key, canned fallback used
```

No key is required for the bot to work — this is strictly additive. If the
Grok call fails for any reason (bad key, network, rate limit), the bot logs it
to the terminal and quietly falls back to the normal canned message; a
customer never sees an error. `.env.example` lists the two settings
(`GROK_API_KEY`, optional `GROK_MODEL`).

**Why hybrid instead of Grok answering everything:** a support bot states
policy, and a generative model can invent a refund window that doesn't exist.
Keeping retrieval as the primary responder means the business is never bound
by something Grok made up — Grok only ever sees the leftovers.

---

## Results

```
$ python tests/evaluate.py

  intents 21 | patterns 397 | features 3554
  In-scope accuracy   96.0%  (48/50)
  Asked to clarify    0
  Out-of-scope caught 5/5    (100%)
  Mean top-1 margin   0.416
  RESULT: PASS
```

The test set in `data/test_set.json` is held out: no test sentence appears in
the training patterns, and a script checks for overlap, so this number measures
generalisation rather than memorisation.

**Threshold choice** (`python tests/evaluate.py --sweep`) — accuracy falls off a
cliff above 0.40 as correct matches get rejected, so 0.30 sits in the flat zone:

| threshold | accuracy | off-topic caught |
|-----------|----------|------------------|
| 0.24      | 96%      | 100%             |
| **0.30**  | **96%**  | **100%**         |
| 0.44      | 84%      | 100%             |
| 0.56      | 56%      | 100%             |

**Typo robustness** (`--noise`) — random character corruption costs 18 points,
96% → 78%. Char n-grams absorb single-letter slips; heavier corruption still
breaks it. Worth stating plainly rather than claiming immunity.

**Known confusions**, both semantic rather than lexical — both score above the
answer threshold, so the bot answers confidently but wrong rather than asking
to clarify:

| asked | matched | why |
|-------|---------|-----|
| "when are you getting more in" | store_hours | "in" reads like opening hours |
| "will it arrive built" | shipping_info | "arrive" outweighs "built" |

Each is fixable with two or three more distinguishing patterns — the loop below.

---

## Training it on your own business

Everything the bot knows lives in `data/intents.json`. No code changes needed.

```json
{
  "tag": "shipping_info",
  "patterns": ["how long does shipping take", "delivery time", "..."],
  "responses": ["Accessories ship in 1-2 working days..."],
  "quick_replies": ["International shipping", "Track my order"]
}
```

Guidelines that matter in practice:

- **8 to 15 patterns per intent.** Fewer and paraphrases miss. Write how
  customers actually type, typos and all, not how the policy document reads.
- **Two or three responses per intent** so a repeat visitor doesn't get the same
  sentence twice.
- **Vary sentence shape**, not just words. "return policy", "can i send it back"
  and "the jacket doesn't fit" are the same intent in three different shapes.
- **Keep intents apart.** If two intents share most of their vocabulary, either
  merge them or add patterns containing the word that distinguishes them.

Then reload without restarting:

```bash
curl -X POST http://127.0.0.1:5000/api/reload
```

### The improvement loop

1. Run `python tests/evaluate.py` and read the *Confused pairs* section.
2. Open `/api/metrics` and read `unmatched` — real questions the bot missed.
3. Add those questions as patterns under the right intent.
4. Add a few of them to `data/test_set.json` instead if you want to measure
   rather than memorise. Never put the same sentence in both files.
5. Re-run the evaluation. If accuracy dropped, the new patterns collided with an
   existing intent.

---

## Putting it on a real website

One line, anywhere before `</body>`:

```html
<script src="https://your-bot-host.com/widget.js"
        data-api="https://your-bot-host.com"
        data-title="Northwind support"></script>
```

- **WordPress:** Appearance → Theme File Editor → `footer.php`
- **Shopify:** Online Store → Themes → Edit code → `theme.liquid`
- **Static site:** paste it into the HTML

The widget renders inside a **shadow root**, so the host page's CSS cannot leak
in and break it, and its own CSS cannot restyle the host page. That is what makes
"drop it on any site" actually true instead of mostly true.

The demo storefront at `/` is a stand-in customer site with the widget already
installed — it exists to prove the integration touches nothing else on the page.

Accessibility is built in rather than bolted on: `Escape` closes the panel, focus
returns to the launcher, the message log is announced via `aria-live`, focus
rings are visible, and `prefers-reduced-motion` is respected.

---

## Measuring engagement

Every turn is appended to `logs/conversations.jsonl`. `GET /api/metrics` turns
that into:

| metric | meaning |
|--------|---------|
| `containment_rate` | share of chats resolved without a human — the number that justifies the bot commercially |
| `fallback_rate` | share of turns it couldn't match; above ~15% means thin training data |
| `turns_per_session` | engagement depth; 1.0 means people ask once and leave |
| `helpful_rate` | thumbs up share, collected after the third reply |
| `unmatched` | the retraining queue |

Put `/api/metrics` behind authentication before going live.

---

## Files

```
app.py                  Flask server, chat API, CORS for cross-origin embedding
chatbot/engine.py       training, scoring, confidence gate, slot filling
chatbot/preprocess.py   normalisation, synonyms, order-number extraction
chatbot/analytics.py    conversation logging and engagement metrics
chatbot/grok.py         optional generative fallback via xAI's Grok API
.env.example            template for GROK_API_KEY / GROK_MODEL
data/intents.json       ALL training data and replies — edit this one
data/test_set.json      held-out evaluation set
static/widget.js        embeddable widget, shadow DOM isolated
templates/index.html    demo storefront
tests/evaluate.py       accuracy, threshold sweep, typo robustness
embed.html              the snippet to paste into a customer site
```

---

## Before production

This runs as a demo. Three things need changing for real use:

1. **Sessions are in memory** (`SESSIONS` in `app.py`). Behind gunicorn with
   several workers a user would lose context between requests. Move it to Redis.
2. **`ALLOWED_ORIGINS` defaults to `*`.** Set it to your real domain:
   `export ALLOWED_ORIGINS=https://yourshop.com`.
3. **Order lookups are simulated.** `slot_response` in `intents.json` returns a
   fixed status; wire it to the real order API in `engine.py::_answer`.

Rate limiting on `/api/chat` is also worth adding — the endpoint is public.
