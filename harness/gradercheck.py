import random
from collections import Counter

from . import config
from .scorers import SCORERS
from .text import sentences, squash

REFERENCE_QUOTE_WORDS = 20


def reference_quote(narrative):
    for s in sentences(narrative):
        words = s.split()
        if len(words) >= 8:
            return " ".join(words[:REFERENCE_QUOTE_WORDS])
    words = squash(narrative).split()
    return " ".join(words[:REFERENCE_QUOTE_WORDS])


def reference_output(case):
    return {"complaint_id": case["complaint_id"], "product": case["product"],
            "escalate": case["expected_escalate"], "quote": reference_quote(case["narrative"])}


def _swap_word(quote, rng):
    words = quote.split()
    candidates = [i for i, w in enumerate(words) if w.isalpha() and len(w) > 3]
    if not candidates:
        return None
    i = rng.choice(candidates)
    words[i] = "zebra" if words[i].lower() != "zebra" else "walrus"
    return " ".join(words)


def _probes(cases, rng):
    products = sorted({c["product"] for c in cases})
    majority = Counter(c["product"] for c in cases).most_common(1)[0][0]
    probes = []
    for idx, case in enumerate(cases):
        ref = reference_output(case)
        other = cases[(idx + 1) % len(cases)]

        probes.append(("accepts a correct answer", "correct", case, ref))

        wrong = next(p for p in products if p != case["product"]) if len(products) > 1 else None
        if wrong:
            probes.append(("planted: wrong product", "mistake", case, {**ref, "product": wrong}))
        probes.append(("planted: escalation flipped", "mistake", case, {**ref, "escalate": not ref["escalate"]}))
        swapped = _swap_word(ref["quote"], rng)
        if swapped:
            probes.append(("planted: one word changed in quote", "mistake", case, {**ref, "quote": swapped}))
        borrowed = reference_quote(other["narrative"])
        if other["complaint_id"] != case["complaint_id"] and squash(borrowed).lower() not in squash(case["narrative"]).lower():
            probes.append(("planted: quote from another complaint", "mistake", case, {**ref, "quote": borrowed}))

        probes.append(("shortcut: quote is the whole complaint", "shortcut", case, {**ref, "quote": case["narrative"]}))
        first_word = next((w for w in case["narrative"].split() if w.isalpha() and len(w) > 3), None)
        if first_word:
            probes.append(("shortcut: one-word quote", "shortcut", case, {**ref, "quote": first_word}))
        if "XXXX" in case["narrative"]:
            probes.append(("shortcut: quote is only redaction marks", "shortcut", case, {**ref, "quote": "XXXX"}))
        probes.append(("shortcut: empty quote", "shortcut", case, {**ref, "quote": ""}))
        probes.append(("shortcut: always escalate", "shortcut", case, {**ref, "escalate": True}))
        probes.append(("shortcut: always the most common product", "shortcut", case, {**ref, "product": majority}))
    return probes


def _changed_field(probe_name):
    if "product" in probe_name:
        return "product"
    if "escalat" in probe_name:
        return "escalate"
    return "quote"


SCORER_FIELD = {
    "product_match": "product",
    "action_match": "escalate",
    "guardrail": "escalate",
    "faithful_substring": "quote",
    "faithful_bounded": "quote",
}


def run(cases, seed=config.SEED):
    rng = random.Random(seed)
    probes = _probes(cases, rng)
    rows = {}
    for probe_name, kind, case, output in probes:
        for scorer_name, fn in SCORERS.items():
            if kind != "correct" and SCORER_FIELD[scorer_name] != _changed_field(probe_name):
                continue
            if scorer_name == "guardrail" and kind == "mistake" and not case["expected_escalate"]:
                continue
            if kind != "correct":
                ref = reference_output(case)
                field = _changed_field(probe_name)
                if output[field] == ref[field]:
                    continue
            key = (scorer_name, probe_name, kind)
            r = rows.setdefault(key, {"scorer": scorer_name, "probe": probe_name, "kind": kind,
                                      "n": 0, "passed": 0})
            r["n"] += 1
            r["passed"] += bool(fn(output, case))
    table = []
    for r in rows.values():
        if r["kind"] == "correct":
            r["result"] = f"accepted {r['passed']}/{r['n']}"
            r["good"] = r["passed"] == r["n"]
        else:
            caught = r["n"] - r["passed"]
            r["caught"] = caught
            r["result"] = f"caught {caught}/{r['n']}"
            r["good"] = caught == r["n"]
        table.append(r)
    order = {"correct": 0, "mistake": 1, "shortcut": 2}
    table.sort(key=lambda r: (r["scorer"], order[r["kind"]], r["probe"]))
    return table
