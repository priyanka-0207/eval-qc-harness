import json
import re
import time
from datetime import datetime

from .. import config, store
from .core import run_episode
from .llm_agent import DEFAULT_MODEL, OllamaClient, make_agent
from .run import FAMILIES, build_tasks


FREE_TEXT_FIELDS = ("quote",)


def _key(obj):
    if isinstance(obj, dict):
        obj = {k: v for k, v in obj.items() if k not in FREE_TEXT_FIELDS}
    return json.dumps(obj, sort_keys=True, default=str)


def _slug(model):
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def summarize(trajs, families):
    by_family = {}
    for fam in families:
        rows = [t for t in trajs if t["family"] == fam]
        if rows:
            by_family[fam] = {"passed": sum(t["reward"] for t in rows), "tasks": len(rows)}
    by_task = {}
    for t in trajs:
        cell = by_task.setdefault(t["task_id"], {"family": t["family"], "passed": 0, "attempts": 0})
        cell["passed"] += t["reward"]
        cell["attempts"] += 1
    steps = [len(t["steps"]) for t in trajs]
    return {
        "by_family": by_family,
        "all": {"passed": sum(t["reward"] for t in trajs), "tasks": len(trajs)},
        "by_task": by_task,
        "rewarded_wrong_answers": [t["task_id"] for t in trajs if t["reward"] == 1 and not t["matches_reference"]],
        "tool_errors": sum(t["tool_errors"] for t in trajs),
        "avg_steps": round(sum(steps) / len(steps), 1) if steps else 0,
        "hit_step_limit": [t["task_id"] for t in trajs if len(t["steps"]) >= 15 and t["steps"][-1]["tool"] != "submit"],
    }


def render(results, path):
    s = results["summary"]
    fams = [f.NAME for f in FAMILIES]
    lines = [f"# Open-model run: {results['model']}", "",
             f"Generated {results['generated_at']}. {results['attempts']} attempt(s) per task, temperature "
             f"{results['temperature']}. The model runs locally through Ollama. Rewards are the same code checks "
             "the scripted agents get.", "",
             "| Agent | " + " | ".join(fams) + " | All |", "|---" * (len(fams) + 2) + "|"]
    rows = {results["model"]: {**s["by_family"], "all": s["all"]}}
    rows.update(results.get("baselines", {}))
    for agent, row in rows.items():
        cells = [f"{row[f]['passed']}/{row[f]['tasks']}" if f in row else "-" for f in fams]
        lines.append(f"| {agent} | " + " | ".join(cells) + f" | {row['all']['passed']}/{row['all']['tasks']} |")
    lines += ["", f"Average steps per task: {s['avg_steps']}. Tool errors: {s['tool_errors']}. "
              f"Rewarded wrong answers: {len(s['rewarded_wrong_answers'])}. "
              f"Model calls: {results['model_calls']} in {results['minutes']} minutes.", "",
              "## Per task", "", "| Task | Passed |", "|---|---|"]
    for tid, cell in s["by_task"].items():
        lines.append(f"| {tid} | {cell['passed']}/{cell['attempts']} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run(model=DEFAULT_MODEL, attempts=1, temperature=0.0, task_ids=None, log=print):
    tasks = build_tasks()
    reference = {}
    for fam in FAMILIES:
        for task in tasks[fam.NAME]:
            reference[task["id"]] = _key(run_episode(task, fam, fam.oracle(task), "oracle")["answer"])
    out = config.REPORTS / "env_llm" / _slug(model)
    trace_path = out / "traces.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text("", encoding="utf-8")
    temp = temperature if attempts == 1 else max(temperature, 0.7)
    trajs, calls, seconds = [], 0, 0.0
    total = sum(1 for fam in FAMILIES for t in tasks[fam.NAME] if not task_ids or t["id"] in task_ids) * attempts
    for attempt in range(attempts):
        client = OllamaClient(model, temperature=temp, seed=attempt)
        agent = make_agent(client)
        for fam in FAMILIES:
            for task in tasks[fam.NAME]:
                if task_ids and task["id"] not in task_ids:
                    continue
                started = time.time()
                traj = run_episode(task, fam, agent, model)
                traj.update({
                    "attempt": attempt,
                    "seconds": round(time.time() - started, 1),
                    "tool_errors": sum(1 for st in traj["steps"] if not st["obs"].get("ok")),
                    "matches_reference": _key(traj["answer"]) == reference[task["id"]],
                })
                trajs.append(traj)
                with trace_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(traj, default=str) + "\n")
                log(f"[{len(trajs)}/{total}] {task['id']} attempt {attempt + 1}: reward {traj['reward']}, "
                    f"{len(traj['steps'])} steps, {traj['seconds']}s")
        calls += client.calls
        seconds += client.seconds
    baselines = {}
    base_path = config.REPORTS / "env" / "results.json"
    if base_path.exists():
        rates = store.read_json(base_path)["pass_rates"]
        baselines = {k: rates[k] for k in ("oracle", "v1", "v2") if k in rates}
    results = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "model": model, "attempts": attempts, "temperature": temp,
        "model_calls": calls, "minutes": round(seconds / 60, 1),
        "summary": summarize(trajs, [f.NAME for f in FAMILIES]),
        "baselines": baselines,
    }
    store.write_json(out / "results.json", results)
    report = render(results, out / "report.md")
    return {**results, "report": report, "out": out}
