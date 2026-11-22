import json
from datetime import datetime

from .. import config, store
from . import dataqc, retrieval, taskqc, tickets
from .core import run_episode

FAMILIES = (tickets, dataqc, retrieval)
EXAMPLE_TASK = "tickets-03"


def build_tasks(dirty=False):
    return {fam.NAME: fam.make_tasks(dirty=dirty) for fam in FAMILIES}


def run_agents(tasks):
    runs = {}
    for fam in FAMILIES:
        for name, agent in fam.AGENTS.items():
            for task in tasks[fam.NAME]:
                runs.setdefault(name, []).append(run_episode(task, fam, agent, name))
    return runs


def pass_rates(runs):
    table = {}
    for agent, trajs in runs.items():
        row = {}
        for fam in FAMILIES:
            rewards = [t["reward"] for t in trajs if t["family"] == fam.NAME]
            if rewards:
                row[fam.NAME] = {"passed": sum(rewards), "tasks": len(rewards)}
        rewards = [t["reward"] for t in trajs]
        row["all"] = {"passed": sum(rewards), "tasks": len(rewards)}
        table[agent] = row
    return table


def regression(before, after):
    b = {t["task_id"]: t["reward"] for t in before}
    fixed = [t["task_id"] for t in after if b.get(t["task_id"]) == 0 and t["reward"] == 1]
    broken = [t["task_id"] for t in after if b.get(t["task_id"]) == 1 and t["reward"] == 0]
    return {"fixed": fixed, "broken": broken}


def _rate(cell):
    return f"{cell['passed']}/{cell['tasks']}" if cell else "-"


def render(results, path):
    lines = [f"# RL environment report ({'dirty' if results['dirty'] else 'clean'} task set)", "",
             f"Generated {results['generated_at']}. All tasks are synthetic. Every reward is deterministic code.", "",
             f"Tasks: {results['task_count']} ({', '.join(f'{k} {v}' for k, v in results['tasks_per_family'].items())})", "",
             f"## Task QC gate: {results['gate']['gate']}", "", "| Check | Status | Detail |", "|---|---|---|"]
    for c in results["gate"]["checks"]:
        lines.append(f"| {c['check']} | {c['status']} | {c['detail']} |")
    fams = [f.NAME for f in FAMILIES]
    lines += ["", "## Pass rate by agent", "", "| Agent | " + " | ".join(fams) + " | All |",
              "|---" * (len(fams) + 2) + "|"]
    for agent, row in results["pass_rates"].items():
        lines.append(f"| {agent} | " + " | ".join(_rate(row.get(f)) for f in fams) + f" | {_rate(row['all'])} |")
    reg = results["regression"]
    lines += ["", "## Regression: v1 to v2", "",
              f"Fixed {len(reg['fixed'])}: {', '.join(reg['fixed']) or 'none'}", "",
              f"Broken {len(reg['broken'])}: {', '.join(reg['broken']) or 'none'}", ""]
    if results["gate"]["hacks"]:
        lines += ["## Rewarded wrong answers", "", "| Shortcut | Task | Answer |", "|---|---|---|"]
        for h in results["gate"]["hacks"]:
            lines.append(f"| {h['agent']} | {h['task_id']} | `{json.dumps(h['answer'])[:120]}` |")
        lines.append("")
    ex = results["example"]
    if ex:
        lines += [f"## Example trajectory: {ex['agent']} on {ex['task_id']} (reward {ex['reward']})", "", "```"]
        for s in ex["steps"]:
            obs = s["obs"].get("result", s["obs"].get("error"))
            lines.append(f"{s['step']}. {s['tool']} {json.dumps(s['args'])} -> {json.dumps(obs)[:160]}")
        lines += ["```", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(dirty=False):
    tasks = build_tasks(dirty)
    gate = taskqc.run(FAMILIES, tasks)
    runs = {**gate["runs"], **run_agents(tasks)}
    out = config.REPORTS / ("env_dirty" if dirty else "env")
    for agent, trajs in runs.items():
        store.write_jsonl(out / "traces" / f"{agent}.jsonl", trajs)
    example = next((t for t in runs.get("v2", []) if t["task_id"] == EXAMPLE_TASK), None)
    results = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "dirty": dirty,
        "task_count": sum(len(v) for v in tasks.values()),
        "tasks_per_family": {k: len(v) for k, v in tasks.items()},
        "gate": {k: v for k, v in gate.items() if k != "runs"},
        "pass_rates": pass_rates(runs),
        "regression": regression(runs["v1"], runs["v2"]),
        "example": example,
    }
    store.write_json(out / "results.json", results)
    report = render(results, out / "report.md")
    return {**results, "report": report, "out": out}
