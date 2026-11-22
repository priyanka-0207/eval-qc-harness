import argparse
import shutil
import sys

from harness import config

DATASETS = {
    "cfpb-200": config.ROOT / "datasets" / "cfpb-200",
}


def _cfpb_dir():
    folder = DATASETS["cfpb-200"]
    if not any(folder.glob("*.csv")):
        exports = sorted(config.BRONZE_DIR.glob("*.csv"))
        if not exports:
            sys.exit(f"No CSV in {folder}. Export the narratives from Databricks (see datasets/cfpb-200/README.md).")
        folder.mkdir(parents=True, exist_ok=True)
        for f in exports:
            shutil.copy2(f, folder / f.name)
        print(f"copied {len(exports)} export file(s) from {config.BRONZE_DIR} to {folder}")
    return folder


def _print_headline(h):
    a = h["agent"]
    print()
    print(f"{h['dataset']} run, {h['eval_rows']} test cases")
    print(f"  blocked before scoring:  {h['blocked_rows']} of {h['bronze_rows']} raw rows  {h['blocked_by_step']}")
    print(f"  near copies kept out of the test set: {h['eval_pool_near_copies_removed']}")
    print(f"  leaked in a naive split: {h['naive_leaked_cases']} of {h['naive_eval_rows']} "
          f"(naive gate {h['gate_naive']}, clean gate {h['gate_clean']})")
    for key, label in (("faithful_quote", "faithful quote"), ("escalation_decision", "escalation decision"),
                       ("guardrail", "required escalations"), ("over_escalation", "over-escalation")):
        r = a[key]
        print(f"  {label:22} {r['passed']}/{r['n']}  {r['rate']:.1%}" if r["rate"] is not None else f"  {label}: n/a")
    if h["example"]:
        ex = h["example"]
        print(f"  caught example: test #{ex['eval_id']} ~ corpus #{ex['corpus_id']} "
              f"(Jaccard {ex['jaccard']}, agent top-1 was the twin: {ex['agent_top1_is_twin']})")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the eval QC harness on one dataset.")
    parser.add_argument("--dataset", choices=["cfpb-200", "synthetic"], default="cfpb-200")
    parser.add_argument("--judge", action="store_true", help="add the LLM judge (needs an API key in .env)")
    parser.add_argument("--ci", action="store_true", help="exit 1 if the clean split fails the QC gate")
    parser.add_argument("--publish", action="store_true", help="rebuild docs/ for GitHub Pages after the run")
    args = parser.parse_args(argv)

    if args.dataset == "synthetic":
        from harness import demo
        result = demo.run(use_judge=args.judge)
        base = config.ROOT / "demo_run"
    else:
        config.use_root(config.ROOT)
        config.BRONZE_DIR = _cfpb_dir()
        from harness.cli import run_all
        result = run_all(ci=False, use_judge=args.judge)
        base = config.ROOT
    from harness import store
    _print_headline(store.read_json(base / "reports" / "results.json")["headline"])
    if args.publish:
        config.use_root(config.ROOT)
        from harness.cli import publish
        publish()
    if args.ci and result["gates"]["time"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
