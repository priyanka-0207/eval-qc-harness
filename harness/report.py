from . import config


def _pct(x):
    return "n/a" if x is None else f"{x:.1%}"


def _metric_row(name, totals):
    t = totals[name]
    return f"{_pct(t['rate'])} ({t['passed']}/{t['n']})"


METRIC_LABELS = {
    "product_match": "Product correct",
    "action_match": "Escalation decision correct",
    "guardrail": "Required escalations made",
    "faithful_bounded": "Quote is verbatim, 5 to 40 words, at most half the complaint",
    "over_escalation": "Escalated when not required (lower is better)",
}


def render(results):
    lines = ["# Eval QC report", ""]
    lines += [f"Source: {', '.join(s['file'] for s in results['sources'])}", ""]
    if any("NOT_REAL" in s["file"] for s in results["sources"]):
        lines += ["> Demo run on generated sample rows. These are not real complaints, and the scores say "
                  "nothing about real agent performance. They only show that each part of the harness works.", ""]

    lines += ["## 1. Data lineage", "", "| Step | Rows | Dropped |", "|---|---:|---:|"]
    for s in results["silver_manifest"]["steps"]:
        lines.append(f"| {s['step']} | {s['rows']} | {s['dropped']} |")
    lines += ["", f"Reconciled: {results['silver_manifest']['reconciled']}", ""]

    lines += ["## 2. Dataset QC gate", ""]
    for split, qc in results["qc"].items():
        info = results["splits"][split]
        lines += [f"### Split: {split} (gate {qc['gate']})", "", "```", *(f"{k}: {v}" for k, v in info.items()), "```", "",
                  "| Check | Status | Detail |", "|---|---|---|"]
        for c in qc["checks"]:
            lines.append(f"| {c['check']} | {c['status']} | {c['detail']} |")
        lines.append("")

    lines += ["## 3. Agent scores", "", "| Metric | " + " | ".join(f"{a} on {s}" for s, a in results["runs"]) + " |",
              "|---|" + "---:|" * len(results["runs"])]
    for m in METRIC_LABELS:
        cells = [_metric_row(m, results["runs"][(s, a)]["totals"]) for s, a in results["runs"]]
        lines.append(f"| {METRIC_LABELS[m]} | " + " | ".join(cells) + " |")
    lines.append("")

    lines += ["## 4. Regression: v1_nearest to v2_vote on the clean split", "",
              "| Metric | Fixed | Broken | Broken examples |", "|---|---:|---:|---|"]
    for m, r in results["regression"].items():
        lines.append(f"| {METRIC_LABELS[m]} | {r['fixed']} | {r['broken']} | {', '.join(r['broken_examples']) or '-'} |")
    lines.append("")

    lines += ["## 5. Grader QC", "",
              "Each scorer gets correct answers it should accept, planted mistakes it should reject, "
              "and cheating answers it should reject.", "",
              "| Scorer | Probe | Result | OK |", "|---|---|---|---|"]
    for r in results["gradercheck"]:
        lines.append(f"| {r['scorer']} | {r['probe']} | {r['result']} | {'yes' if r['good'] else 'NO'} |")
    lines.append("")

    path = config.REPORTS / "report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
