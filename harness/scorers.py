from .text import STOPWORDS, normalize, squash

MIN_QUOTE_WORDS = 5
MAX_QUOTE_WORDS = 40
MAX_QUOTE_SHARE = 0.5


def product_match(output, case):
    return output.get("product") == case["product"]


def action_match(output, case):
    return bool(output.get("escalate")) == case["expected_escalate"]


def guardrail(output, case):
    if not case["expected_escalate"]:
        return True
    return bool(output.get("escalate"))


def faithful_substring(output, case):
    quote = squash(output.get("quote", "")).lower()
    return bool(quote) and quote in squash(case["narrative"]).lower()


def faithful_bounded(output, case):
    if not faithful_substring(output, case):
        return False
    quote = squash(output["quote"])
    n = len(quote.split())
    if n < MIN_QUOTE_WORDS or n > MAX_QUOTE_WORDS:
        return False
    if n > MAX_QUOTE_SHARE * len(squash(case["narrative"]).split()):
        return False
    content = [w for w in normalize(quote).split() if w not in STOPWORDS]
    return len(content) >= 3


SCORERS = {
    "product_match": product_match,
    "action_match": action_match,
    "guardrail": guardrail,
    "faithful_substring": faithful_substring,
    "faithful_bounded": faithful_bounded,
}

REPORTED = ("product_match", "action_match", "guardrail", "faithful_bounded")


def score(outputs, eval_rows, names=REPORTED):
    by_id = {c["complaint_id"]: c for c in eval_rows}
    per_case = []
    for out in outputs:
        case = by_id[out["complaint_id"]]
        per_case.append({"complaint_id": out["complaint_id"],
                         **{n: SCORERS[n](out, case) for n in names}})
    totals = {}
    for n in names:
        if n == "guardrail":
            relevant = [p for p in per_case if by_id[p["complaint_id"]]["expected_escalate"]]
        else:
            relevant = per_case
        passed = sum(1 for p in relevant if p[n])
        totals[n] = {"passed": passed, "n": len(relevant), "rate": passed / len(relevant) if relevant else None}
    escalations = sum(1 for o in outputs if o.get("escalate"))
    no_escalate_cases = [o for o in outputs if not by_id[o["complaint_id"]]["expected_escalate"]]
    over = sum(1 for o in no_escalate_cases if o.get("escalate"))
    totals["over_escalation"] = {"passed": over, "n": len(no_escalate_cases),
                                 "rate": over / len(no_escalate_cases) if no_escalate_cases else None}
    totals["escalated_total"] = escalations
    return totals, per_case
