import argparse
import sys
from datetime import datetime

from . import bronze, config, dashboard, gold, gradercheck, judgecheck, labels, qc, regression, report, silver, store
from .agent import run_agent
from .judge import make_judge
from .scorers import score

AGENT_NAMES = ("v1_nearest", "v2_vote")


def _judge_section(use_judge, judge_client, eval_rows, run):
    if not use_judge:
        return {"status": "skipped", "message": "Run with --judge to add the LLM judge."}
    judge = judge_client or make_judge()
    if judge is None:
        return {"status": "no_key",
                "message": f"No API key found. Add {config.JUDGE_KEY_NAME}=... to the .env file in the project folder."}
    try:
        result = judgecheck.run(judge, eval_rows, run["outputs"], run["per_case"])
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
    return {"status": "ran", **result}


def run_all(ci=False, use_judge=False, judge_client=None):
    bronze_rows, sources = bronze.load()
    silver_rows, manifest = silver.build(bronze_rows)

    splits = {}
    corpus, eval_rows, info = gold.time_split(silver_rows)
    gold.write_split("time", corpus, eval_rows, info)
    splits["time"] = (corpus, eval_rows, info)
    corpus_n, eval_n, info_n = gold.naive_split(bronze_rows)
    gold.write_split("naive", corpus_n, eval_n, info_n)
    splits["naive"] = (corpus_n, eval_n, info_n)

    qc_results = {
        "time": qc.run(splits["time"][0], splits["time"][1], manifest),
        "naive": qc.run(splits["naive"][0], splits["naive"][1]),
    }

    runs = {}
    for split in ("time", "naive"):
        c, e, _ = splits[split]
        for name in AGENT_NAMES:
            outputs = run_agent(name, c, e)
            totals, per_case = score(outputs, e)
            runs[(split, name)] = {"outputs": outputs, "totals": totals, "per_case": per_case}
            store.write_jsonl(config.REPORTS / "traces" / f"{split}_{name}.jsonl",
                              [{**o, "scores": p} for o, p in zip(outputs, per_case)])

    reg = regression.compare(runs[("time", "v1_nearest")]["per_case"], runs[("time", "v2_vote")]["per_case"])
    grader = gradercheck.run(splits["time"][1])
    judge_result = _judge_section(use_judge, judge_client, splits["time"][1], runs[("time", "v2_vote")])

    results = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sources": sources,
        "silver_manifest": manifest,
        "splits": {k: v[2] for k, v in splits.items()},
        "qc": qc_results,
        "runs": runs,
        "regression": reg,
        "gradercheck": grader,
        "judge": judge_result,
        "eval_rows": {k: v[1] for k, v in splits.items()},
    }
    path = report.render(results)
    html_path = dashboard.render(results)
    store.write_json(config.REPORTS / "results.json", {
        **{k: v for k, v in results.items() if k not in ("runs", "eval_rows")},
        "runs": {f"{s}/{a}": r["totals"] for (s, a), r in runs.items()},
    })
    labels.export(splits["time"][1], runs[("time", "v2_vote")]["outputs"], runs[("time", "v2_vote")]["per_case"])

    print(f"dashboard: {html_path}")
    print(f"report:    {path}")
    for split, q in qc_results.items():
        print(f"QC gate {split}: {q['gate']}")
    for (s, a), r in runs.items():
        t = r["totals"]
        print(f"{s:6} {a:11} product {t['product_match']['rate']:.3f}  action {t['action_match']['rate']:.3f}  "
              f"guardrail {t['guardrail']['rate'] if t['guardrail']['rate'] is not None else float('nan'):.3f}  "
              f"quote {t['faithful_bounded']['rate']:.3f}")
    if judge_result["status"] == "ran":
        print(f"judge: agreement with code scorer {judge_result['agreement_with_code_scorer']:.3f}, "
              f"{judge_result['api_calls_this_run']} new API calls")
    else:
        print(f"judge: {judge_result['message']}")
    if ci and qc_results["time"]["gate"] != "PASS":
        sys.exit(1)
    return {"report": path, "dashboard": html_path, "gates": {k: v["gate"] for k, v in qc_results.items()},
            "totals": {k: v["totals"] for k, v in runs.items()}, "judge": judge_result}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m harness")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_all = sub.add_parser("all", help="bronze to report, end to end")
    p_all.add_argument("--ci", action="store_true", help="exit 1 if the clean split fails the QC gate")
    p_all.add_argument("--judge", action="store_true", help="add the LLM judge (needs an API key in .env)")
    sub.add_parser("agreement", help="scorer vs your labels in labels/label_sheet.csv")
    sub.add_parser("publish", help="copy the latest dashboard to docs/index.html for GitHub Pages")
    p_demo = sub.add_parser("demo", help="full run on generated sample rows, written to demo_run/")
    p_demo.add_argument("--judge", action="store_true", help="add the LLM judge (needs an API key in .env)")
    args = parser.parse_args(argv)
    if args.cmd == "all":
        run_all(ci=args.ci, use_judge=args.judge)
    elif args.cmd == "demo":
        from . import demo
        demo.run(use_judge=args.judge)
    elif args.cmd == "agreement":
        print(labels.agreement())
    elif args.cmd == "publish":
        publish()


def publish():
    import shutil
    real = config.ROOT / "reports" / "site"
    demo_site = config.ROOT / "demo_run" / "reports" / "site"
    source = real if (real / "index.html").exists() else demo_site
    if not (source / "index.html").exists():
        sys.exit("No dashboard found. Run `python -m harness all` (or `demo`) first.")
    docs = config.ROOT / "docs"
    docs.mkdir(exist_ok=True)
    for item in docs.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    shutil.copytree(source, docs, dirs_exist_ok=True)
    kind = "real data" if source == real else "demo data"
    pages = sorted(str(f.relative_to(docs)).replace("\\", "/") for f in docs.rglob("index.html"))
    print(f"published {kind} dashboard to {docs}: {', '.join(pages)}")
    return docs
