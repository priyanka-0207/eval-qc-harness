import argparse
import sys
from datetime import datetime

from . import bronze, config, dashboard, gold, gradercheck, headline, judgecheck, labels, qc, regression, report, silver, store
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
    results["headline"] = headline.build(results, splits, runs)
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
    p_env = sub.add_parser("env", help="RL environment: 30 tasks, task QC gate, agents, regression report")
    p_env.add_argument("--dirty", action="store_true", help="add 3 planted bad tasks to show the gate catching them")
    p_env.add_argument("--ci", action="store_true", help="exit 1 if the task QC gate fails")
    p_llm = sub.add_parser("env-llm", help="RL environment with an open model as the agent, run locally through Ollama")
    p_llm.add_argument("--model", default="gemma4", help="Ollama model name (default gemma4)")
    p_llm.add_argument("--attempts", type=int, default=1, help="attempts per task (more than 1 samples at temperature 0.7)")
    p_llm.add_argument("--task", action="append", help="run only this task id (repeatable)")
    args = parser.parse_args(argv)
    if args.cmd == "all":
        default_set = config.ROOT / "datasets" / "cfpb-200"
        if not any(config.BRONZE_DIR.glob("*.csv")) and any(default_set.glob("*.csv")):
            print(f"no CSV in {config.BRONZE_DIR}, using {default_set}")
            config.BRONZE_DIR = default_set
        run_all(ci=args.ci, use_judge=args.judge)
    elif args.cmd == "demo":
        from . import demo
        demo.run(use_judge=args.judge)
    elif args.cmd == "env-llm":
        from .env import llm_run
        res = llm_run.run(model=args.model, attempts=args.attempts, task_ids=args.task)
        s = res["summary"]
        print(f"report: {res['report']}")
        print(f"{args.model}: {s['all']['passed']}/{s['all']['tasks']} passed "
              + ", ".join(f"{k} {v['passed']}/{v['tasks']}" for k, v in s["by_family"].items()))
        print(f"rewarded wrong answers: {len(s['rewarded_wrong_answers'])}, tool errors: {s['tool_errors']}")
    elif args.cmd == "env":
        run_env(dirty=args.dirty, ci=args.ci)
    elif args.cmd == "agreement":
        print(labels.agreement())
    elif args.cmd == "publish":
        publish()


def run_env(dirty=False, ci=False):
    from .env import run as env_run
    res = env_run.run(dirty=dirty)
    print(f"report:    {res['report']}")
    print(f"tasks:     {res['task_count']} ({', '.join(f'{k} {v}' for k, v in res['tasks_per_family'].items())})")
    print(f"task QC gate: {res['gate']['gate']}")
    for c in res["gate"]["checks"]:
        print(f"  {c['status']}  {c['check']}: {c['detail']}")
    for agent, row in res["pass_rates"].items():
        cells = "  ".join(f"{k} {v['passed']}/{v['tasks']}" for k, v in row.items())
        print(f"{agent:17} {cells}")
    reg = res["regression"]
    print(f"v1 -> v2: fixed {len(reg['fixed'])}, broken {len(reg['broken'])} {reg['broken']}")
    if ci and res["gate"]["gate"] != "PASS":
        sys.exit(1)
    return res


OLD_PAGES = ("data", "agent", "graders", "judge")


def publish():
    import shutil
    from . import landing
    sources = {"real": config.ROOT / "reports", "synthetic": config.ROOT / "demo_run" / "reports"}
    found = {k: v for k, v in sources.items() if (v / "site" / "index.html").exists() and (v / "results.json").exists()}
    if not found:
        sys.exit("No dashboard found. Run `python run.py --dataset cfpb-200` (or `--dataset synthetic`) first.")
    docs = config.ROOT / "docs"
    docs.mkdir(exist_ok=True)
    for f in sorted(docs.rglob("*"), key=lambda p: -len(p.parts)):
        try:
            f.rmdir() if f.is_dir() else f.unlink()
        except OSError:
            pass
    for kind, base in found.items():
        shutil.copytree(base / "site", docs / kind, dirs_exist_ok=True)
    lead = "real" if "real" in found else "synthetic"
    head = store.read_json(found[lead] / "results.json").get("headline")
    if head is None:
        sys.exit(f"{found[lead] / 'results.json'} has no headline. Re-run the {lead} dataset first.")
    from .env import page as env_page
    has_env = env_page.build(docs / "env" / "index.html") is not None
    (docs / "index.html").write_text(landing.render(head, "real" in found, "synthetic" in found, has_env=has_env),
                                     encoding="utf-8")
    old_source = found.get("synthetic", found[lead]) / "site"
    for key in OLD_PAGES:
        (docs / key).mkdir(exist_ok=True)
        html = (old_source / key / "index.html").read_text(encoding="utf-8")
        (docs / key / "index.html").write_text(html.replace('href="../../', 'href="../'), encoding="utf-8")
    (docs / ".nojekyll").write_text("", encoding="utf-8")
    if landing.update_readme(config.ROOT / "README.md", head):
        print("README results block updated")
    print(f"published to {docs}: overview from the {lead} run, full reports for {', '.join(found)}")
    return docs
