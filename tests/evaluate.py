"""Accuracy and robustness harness.

    python tests/evaluate.py            full report
    python tests/evaluate.py --sweep    tune the answer threshold
    python tests/evaluate.py --noise    typo-robustness check

Three things get measured, because one number hides too much:
  in-scope accuracy   did it pick the right intent
  fallback precision  did it stay quiet on questions it should not answer
  confidence margin   how close the top match was to the runner-up
"""

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chatbot.engine import ChatbotEngine, ANSWER_THRESHOLD, CLARIFY_THRESHOLD  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def load_cases():
    with open(ROOT / "data" / "test_set.json", encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def classify(engine, text, threshold=ANSWER_THRESHOLD):
    """Apply the same gate the live bot uses, so the score is realistic."""
    ranked = engine.rank(text, top_k=2)
    if not ranked:
        return "fallback", 0.0, 0.0
    tag, score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if score < CLARIFY_THRESHOLD:
        return "fallback", score, score - runner_up
    if score < threshold:
        return "clarify", score, score - runner_up
    return tag, score, score - runner_up


def report():
    engine = ChatbotEngine(ROOT / "data" / "intents.json")
    cases = load_cases()

    print("=" * 62)
    print("  NORTHWIND CYCLES BOT — EVALUATION")
    print("=" * 62)
    s = engine.stats
    print(f"  intents {s['intents']} | patterns {s['patterns']} | features {s['features']}")
    print(f"  answer threshold {ANSWER_THRESHOLD} | clarify {CLARIFY_THRESHOLD}")
    print("-" * 62)

    in_scope = [c for c in cases if c["expected"] != "fallback"]
    oos = [c for c in cases if c["expected"] == "fallback"]

    hits, misses, unsure = 0, [], []
    per_intent = defaultdict(lambda: [0, 0])
    confusion = Counter()
    margins = []

    for case in in_scope:
        got, score, margin = classify(engine, case["text"])
        exp = case["expected"]
        per_intent[exp][1] += 1
        margins.append(margin)
        if got == exp:
            hits += 1
            per_intent[exp][0] += 1
        elif got == "clarify":
            unsure.append((case["text"], exp, score))
        else:
            misses.append((case["text"], exp, got, score))
            confusion[(exp, got)] += 1

    oos_correct = sum(
        1 for c in oos if classify(engine, c["text"])[0] in ("fallback", "clarify")
    )

    acc = hits / len(in_scope)
    print(f"  In-scope accuracy   {acc:.1%}  ({hits}/{len(in_scope)})")
    print(f"  Asked to clarify    {len(unsure)}  (soft failures, not wrong answers)")
    print(f"  Out-of-scope caught {oos_correct}/{len(oos)}  ({oos_correct/len(oos):.0%})")
    print(f"  Mean top-1 margin   {sum(margins)/len(margins):.3f}")
    print("-" * 62)

    print("  Per intent (correct / total)")
    for tag in sorted(per_intent):
        ok, total = per_intent[tag]
        flag = "" if ok == total else "   <-- review"
        print(f"    {tag:<24} {ok}/{total}{flag}")

    if misses:
        print("-" * 62)
        print("  Wrong intent")
        for text, exp, got, score in misses:
            print(f"    '{text}'\n      expected {exp} | got {got} ({score:.2f})")

    if unsure:
        print("-" * 62)
        print("  Below answer threshold — bot asks instead of guessing")
        for text, exp, score in unsure:
            print(f"    '{text}' -> {exp} ({score:.2f})")

    if confusion:
        print("-" * 62)
        print("  Confused pairs (add distinguishing patterns to intents.json)")
        for (exp, got), n in confusion.most_common(5):
            print(f"    {exp} mistaken for {got} x{n}")

    print("=" * 62)
    passed = acc >= 0.85 and oos_correct / len(oos) >= 0.8
    print("  RESULT:", "PASS" if passed else "NEEDS WORK")
    print("=" * 62)
    return 0 if passed else 1


def sweep():
    """Show the precision/recall trade-off as the answer gate moves."""
    engine = ChatbotEngine(ROOT / "data" / "intents.json")
    cases = load_cases()
    in_scope = [c for c in cases if c["expected"] != "fallback"]
    oos = [c for c in cases if c["expected"] == "fallback"]

    print(f"{'threshold':>10} {'accuracy':>10} {'oos caught':>12} {'combined':>10}")
    print("-" * 46)
    for t in [round(0.20 + i * 0.04, 2) for i in range(12)]:
        acc = sum(
            1 for c in in_scope if classify(engine, c["text"], t)[0] == c["expected"]
        ) / len(in_scope)
        caught = sum(
            1 for c in oos if classify(engine, c["text"], t)[0] in ("fallback", "clarify")
        ) / len(oos)
        mark = "  <- current" if abs(t - ANSWER_THRESHOLD) < 0.02 else ""
        print(f"{t:>10.2f} {acc:>9.1%} {caught:>11.0%} {(acc+caught)/2:>9.1%}{mark}")


def noise():
    """Robustness: retype each test case with random typos and re-score."""
    rng = random.Random(7)
    engine = ChatbotEngine(ROOT / "data" / "intents.json")
    cases = [c for c in load_cases() if c["expected"] != "fallback"]

    def corrupt(text):
        chars = list(text)
        for _ in range(max(1, len(chars) // 14)):
            i = rng.randrange(len(chars))
            if chars[i] != " ":
                chars[i] = rng.choice("abcdefghijklmnopqrstuvwxyz")
        return "".join(chars)

    clean = sum(1 for c in cases if classify(engine, c["text"])[0] == c["expected"])
    noisy = sum(1 for c in cases if classify(engine, corrupt(c["text"]))[0] == c["expected"])

    print(f"  clean text  {clean/len(cases):.1%}")
    print(f"  with typos  {noisy/len(cases):.1%}")
    print(f"  degradation {(clean-noisy)/len(cases):.1%}  "
          f"(char n-grams absorb part of it; heavy typos still hurt)")


if __name__ == "__main__":
    if "--sweep" in sys.argv:
        sweep()
    elif "--noise" in sys.argv:
        noise()
    else:
        sys.exit(report())
