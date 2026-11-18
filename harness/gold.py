import random
from collections import defaultdict

from . import config, store
from .neardup import near_duplicates
from .silver import parse_date, rule_hits
from .text import squash


def stratified_sample(rows, size, seed):
    rng = random.Random(seed)
    by_product = defaultdict(list)
    for r in rows:
        by_product[r["product"]].append(r)
    for bucket in by_product.values():
        rng.shuffle(bucket)
    picked, products = [], sorted(by_product)
    while len(picked) < size and any(by_product[p] for p in products):
        for p in products:
            if by_product[p] and len(picked) < size:
                picked.append(by_product[p].pop())
    return picked


def time_split(silver, eval_fraction=config.EVAL_FRACTION, size=config.EVAL_SIZE,
               threshold=config.QC_NEAR_DUP_JACCARD, seed=config.SEED):
    dates = sorted(r["date_received"] for r in silver)
    cutoff = dates[int(len(dates) * (1 - eval_fraction))]
    corpus = [r for r in silver if r["date_received"] < cutoff]
    pool = [r for r in silver if r["date_received"] >= cutoff]
    dups = near_duplicates(pool, corpus, threshold)
    dup_ids = {d["eval_id"] for d in dups}
    clean_pool = [r for r in pool if r["complaint_id"] not in dup_ids]
    eval_rows = stratified_sample(clean_pool, size, seed)
    info = {
        "split": "time",
        "cutoff_date": cutoff,
        "corpus_rows": len(corpus),
        "eval_pool_rows": len(pool),
        "eval_pool_near_duplicates_removed": len(dup_ids),
        "eval_rows": len(eval_rows),
    }
    return corpus, eval_rows, info


def naive_split(bronze_rows, size=config.EVAL_SIZE, seed=config.SEED):
    rows = []
    for r in bronze_rows:
        date = parse_date(r["date_received"])
        if r["complaint_id"] and r["product"] and r["narrative"].strip() and date:
            hits = rule_hits(r)
            rows.append({
                "complaint_id": r["complaint_id"], "date_received": date, "product": r["product"],
                "sub_product": r["sub_product"], "issue": r["issue"], "sub_issue": r["sub_issue"],
                "company": r["company"], "state": r["state"], "tags": r["tags"],
                "narrative": squash(r["narrative"]), "rules": hits, "expected_escalate": bool(hits),
            })
    rng = random.Random(seed)
    rng.shuffle(rows)
    eval_rows = stratified_sample(rows, size, seed)
    picked = {id(r) for r in eval_rows}
    corpus = [r for r in rows if id(r) not in picked]
    info = {"split": "naive", "corpus_rows": len(corpus), "eval_rows": len(eval_rows),
            "note": "random split on unfiltered bronze rows, no dedupe, no time order"}
    return corpus, eval_rows, info


def write_split(name, corpus, eval_rows, info):
    folder = config.GOLD / name
    store.write_jsonl(folder / "corpus.jsonl", corpus)
    store.write_jsonl(folder / "eval.jsonl", eval_rows)
    store.write_json(folder / "split.json", info)
    return folder


def load_split(name):
    folder = config.GOLD / name
    return (store.read_jsonl(folder / "corpus.jsonl"), store.read_jsonl(folder / "eval.jsonl"),
            store.read_json(folder / "split.json"))
