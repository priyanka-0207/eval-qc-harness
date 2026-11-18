from collections import Counter

from . import config
from .neardup import near_duplicates
from .text import normalize


def _check(name, passed, detail):
    return {"check": name, "status": "PASS" if passed else "FAIL", "detail": detail}


def run(corpus, eval_rows, silver_manifest=None):
    results = []

    if silver_manifest is not None:
        steps = silver_manifest["steps"]
        detail = "; ".join(f"{s['step']}: {s['rows']} (-{s['dropped']})" for s in steps)
        results.append(_check("row counts reconcile bronze to silver", silver_manifest["reconciled"], detail))

    eval_ids = Counter(r["complaint_id"] for r in eval_rows)
    repeated = [cid for cid, n in eval_ids.items() if n > 1]
    text_counts = Counter(normalize(r["narrative"]) for r in eval_rows)
    dup_rows = sum(n - 1 for n in text_counts.values() if n > 1)
    dup_rate = dup_rows / max(len(eval_rows), 1)
    results.append(_check(
        "no duplicates inside the eval set",
        not repeated and dup_rate <= config.QC_MAX_DUP_RATE,
        f"{len(repeated)} repeated ids, {dup_rows} duplicate narratives ({dup_rate:.1%}, limit {config.QC_MAX_DUP_RATE:.0%})",
    ))

    corpus_ids = {r["complaint_id"] for r in corpus}
    overlap = sorted(set(eval_ids) & corpus_ids)
    results.append(_check(
        "no eval id appears in the retrieval corpus",
        not overlap,
        f"{len(overlap)} eval ids also in corpus" + (f", e.g. {overlap[:3]}" if overlap else ""),
    ))

    dups = near_duplicates(eval_rows, corpus, config.QC_NEAR_DUP_JACCARD)
    results.append(_check(
        "no eval narrative is a near copy of a corpus narrative",
        not dups,
        f"{len(dups)} of {len(eval_rows)} eval cases have a corpus match with 5-word-shingle Jaccard >= {config.QC_NEAR_DUP_JACCARD}",
    ))

    if corpus and eval_rows:
        latest_corpus = max(r["date_received"] for r in corpus)
        earliest_eval = min(r["date_received"] for r in eval_rows)
        results.append(_check(
            "corpus is strictly older than the eval set",
            latest_corpus < earliest_eval,
            f"latest corpus date {latest_corpus}, earliest eval date {earliest_eval}",
        ))

    products = Counter(r["product"] for r in eval_rows)
    thin = {p: n for p, n in products.items() if n < config.QC_MIN_CASES_PER_PRODUCT}
    results.append(_check(
        f"every product has at least {config.QC_MIN_CASES_PER_PRODUCT} eval cases",
        not thin,
        ", ".join(f"{p}: {n}" for p, n in sorted(products.items(), key=lambda x: -x[1])),
    ))

    rules = Counter(rule for r in eval_rows for rule in r["rules"])
    negatives = sum(1 for r in eval_rows if not r["expected_escalate"])
    rule_names = ("vulnerable_consumer_tag", "fraud_or_identity_theft")
    untested = [name for name in rule_names if rules.get(name, 0) < config.QC_MIN_CASES_PER_RULE]
    results.append(_check(
        f"every guardrail rule has at least {config.QC_MIN_CASES_PER_RULE} positive eval cases",
        not untested and negatives >= config.QC_MIN_CASES_PER_RULE,
        ", ".join(f"{name}: {rules.get(name, 0)}" for name in rule_names) + f", no-escalation cases: {negatives}",
    ))

    gate = all(r["status"] == "PASS" for r in results)
    return {"gate": "PASS" if gate else "FAIL", "checks": results, "near_duplicates": dups[:10]}
