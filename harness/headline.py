from . import config
from .neardup import near_duplicates
from .text import squash

SNIPPET_WORDS = 32


def _snippet(text, words=SNIPPET_WORDS):
    parts = squash(text).split()
    return " ".join(parts[:words]) + (" ..." if len(parts) > words else "")


def _rate(totals, name):
    t = totals[name]
    return {"passed": t["passed"], "n": t["n"], "rate": t["rate"]}


def _accuracy(per_case, ids, metric="product_match"):
    rows = [p for p in per_case if p["complaint_id"] in ids]
    if not rows:
        return None
    return {"passed": sum(1 for p in rows if p[metric]), "n": len(rows),
            "rate": sum(1 for p in rows if p[metric]) / len(rows)}


def _pick_example(dups, eval_by_id, corpus_by_id, outputs_by_id):
    scored = []
    for d in dups:
        out = outputs_by_id.get(d["eval_id"], {})
        top1_is_twin = bool(out.get("retrieved")) and out["retrieved"][0] == d["corpus_id"]
        right = out.get("product") == eval_by_id[d["eval_id"]]["product"]
        scored.append(((top1_is_twin and right, top1_is_twin, d["jaccard"] < 1.0, d["jaccard"]), d, out, top1_is_twin))
    if not scored:
        return None
    _, d, out, top1_is_twin = max(scored, key=lambda x: x[0])
    case, twin = eval_by_id[d["eval_id"]], corpus_by_id[d["corpus_id"]]
    return {
        "eval_id": case["complaint_id"], "eval_date": case["date_received"], "eval_product": case["product"],
        "eval_text": _snippet(case["narrative"]),
        "corpus_id": twin["complaint_id"], "corpus_date": twin["date_received"], "corpus_product": twin["product"],
        "corpus_text": _snippet(twin["narrative"]),
        "jaccard": d["jaccard"],
        "agent_top1_is_twin": top1_is_twin,
        "agent_product": out.get("product"),
        "agent_correct": out.get("product") == case["product"],
    }


def build(results, splits, runs):
    steps = results["silver_manifest"]["steps"]
    by_step = {s["step"]: s["dropped"] for s in steps[1:]}
    bronze_rows = steps[0]["rows"]
    time_info = splits["time"][2]

    corpus_n, eval_n, _ = splits["naive"]
    corpus_ids = {r["complaint_id"] for r in corpus_n}
    id_leaks = {r["complaint_id"] for r in eval_n if r["complaint_id"] in corpus_ids}
    dups = near_duplicates(eval_n, corpus_n, config.QC_NEAR_DUP_JACCARD)
    leaked = id_leaks | {d["eval_id"] for d in dups}
    clean_ids = {r["complaint_id"] for r in eval_n} - leaked

    naive_v1 = runs[("naive", "v1_nearest")]
    outputs_by_id = {o["complaint_id"]: o for o in naive_v1["outputs"]}
    example = _pick_example(dups, {r["complaint_id"]: r for r in eval_n},
                            {r["complaint_id"]: r for r in corpus_n}, outputs_by_id)

    qc_time, qc_naive = results["qc"]["time"], results["qc"]["naive"]
    clean_v2 = runs[("time", "v2_vote")]["totals"]
    return {
        "dataset": "synthetic" if any("NOT_REAL" in s["file"] for s in results["sources"]) else "real",
        "bronze_rows": bronze_rows,
        "blocked_rows": sum(by_step.values()),
        "blocked_by_step": by_step,
        "eval_pool_near_copies_removed": time_info["eval_pool_near_duplicates_removed"],
        "eval_rows": time_info["eval_rows"],
        "corpus_rows": time_info["corpus_rows"],
        "cutoff_date": time_info["cutoff_date"],
        "naive_eval_rows": len(eval_n),
        "naive_leaked_cases": len(leaked),
        "naive_id_leaks": len(id_leaks),
        "naive_near_copies": len(dups),
        "gate_clean": qc_time["gate"],
        "gate_naive": qc_naive["gate"],
        "checks_total": len(qc_naive["checks"]),
        "checks_failed_naive": sum(1 for c in qc_naive["checks"] if c["status"] != "PASS"),
        "checks_failed_clean": sum(1 for c in qc_time["checks"] if c["status"] != "PASS"),
        "naive_v1_on_leaked": _accuracy(naive_v1["per_case"], leaked),
        "naive_v1_on_clean": _accuracy(naive_v1["per_case"], clean_ids),
        "product_v1": {"naive": _rate(naive_v1["totals"], "product_match"),
                       "clean": _rate(runs[("time", "v1_nearest")]["totals"], "product_match")},
        "agent": {
            "name": "v2_vote",
            "faithful_quote": _rate(clean_v2, "faithful_bounded"),
            "escalation_decision": _rate(clean_v2, "action_match"),
            "guardrail": _rate(clean_v2, "guardrail"),
            "over_escalation": _rate(clean_v2, "over_escalation"),
            "product": _rate(clean_v2, "product_match"),
        },
        "example": example,
    }
