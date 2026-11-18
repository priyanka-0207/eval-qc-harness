import csv

from . import config

FIELDS = ["complaint_id", "narrative", "gold_product", "agent_product", "agent_quote",
          "scorer_says_product_correct", "your_verdict"]


def export(eval_rows, outputs, per_case, n=50):
    by_out = {o["complaint_id"]: o for o in outputs}
    by_score = {p["complaint_id"]: p for p in per_case}
    path = config.LABELS / "label_sheet.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for case in eval_rows[:n]:
            o = by_out[case["complaint_id"]]
            w.writerow({
                "complaint_id": case["complaint_id"], "narrative": case["narrative"],
                "gold_product": case["product"], "agent_product": o["product"], "agent_quote": o["quote"],
                "scorer_says_product_correct": by_score[case["complaint_id"]]["product_match"],
                "your_verdict": "",
            })
    return path


def cohen_kappa(a, b):
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def agreement(path=None):
    path = path or config.LABELS / "label_sheet.csv"
    scorer, human = [], []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            verdict = row["your_verdict"].strip().lower()
            if verdict not in ("correct", "incorrect"):
                continue
            scorer.append(row["scorer_says_product_correct"] == "True")
            human.append(verdict == "correct")
    if not human:
        return {"labeled": 0, "kappa": None, "agreement": None}
    agree = sum(x == y for x, y in zip(scorer, human)) / len(human)
    return {"labeled": len(human), "agreement": agree, "kappa": cohen_kappa(scorer, human)}
