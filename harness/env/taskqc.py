import hashlib
import json
from collections import Counter

from ..text import shingles
from .core import run_episode

DUP_JACCARD = 0.8
DUP_SHINGLE = 3
MIN_PER_OUTCOME = 2


def null_agent(start):
    yield {"tool": "submit"}


def _check(name, passed, detail):
    return {"check": name, "status": "PASS" if passed else "FAIL", "detail": detail}


def _key(obj):
    return json.dumps(obj, sort_keys=True, default=str)


def _jaccard(a, b):
    return len(a & b) / max(len(a | b), 1)


def run_reference_agents(families, tasks):
    runs = {"oracle": [], "null": []}
    for fam in families:
        for task in tasks[fam.NAME]:
            runs["oracle"].append(run_episode(task, fam, fam.oracle(task), "oracle"))
            runs["null"].append(run_episode(task, fam, null_agent, "null"))
            for name, agent in fam.SHORTCUTS.items():
                runs.setdefault(name, []).append(run_episode(task, fam, agent, name))
    return runs


def run(families, tasks):
    runs = run_reference_agents(families, tasks)
    repeat = run_reference_agents(families, tasks)
    all_tasks = [t for fam in families for t in tasks[fam.NAME]]
    n = len(all_tasks)
    checks = []

    unsolved = [t["task_id"] for t in runs["oracle"] if t["reward"] != 1]
    checks.append(_check("every task is solvable by the reference solution", not unsolved,
                         f"{n - len(unsolved)} of {n} solved" + (f", unsolved: {unsolved}" if unsolved else "")))

    free = [t["task_id"] for t in runs["null"] if t["reward"] != 0]
    checks.append(_check("doing nothing earns no reward", not free,
                         f"null agent rewarded on {len(free)} of {n}" + (f": {free}" if free else "")))

    oracle_answer = {t["task_id"]: _key(t["answer"]) for t in runs["oracle"]}
    hacks, legit = [], 0
    shortcut_names = [k for k in runs if k not in ("oracle", "null")]
    for name in shortcut_names:
        for t in runs[name]:
            if t["reward"] != 1:
                continue
            if _key(t["answer"]) == oracle_answer[t["task_id"]]:
                legit += 1
            else:
                hacks.append({"agent": name, "task_id": t["task_id"], "answer": t["answer"]})
    checks.append(_check("no shortcut agent is rewarded for a wrong answer", not hacks,
                         f"{len(hacks)} rewarded wrong answers, {legit} shortcut passes that match the reference"
                         + (": " + ", ".join(f"{h['agent']} on {h['task_id']}" for h in hacks) if hacks else "")))

    leaks = []
    for fam in families:
        for task in tasks[fam.NAME]:
            visible = (task["prompt"] + " " + _key(task["spec"])).lower()
            found = [s for s in fam.leak_strings(task) if s.lower() in visible]
            if found:
                leaks.append({"task_id": task["id"], "leaked": found})
    checks.append(_check("no task shows its answer in the prompt or spec", not leaks,
                         f"{len(leaks)} tasks leak" + (": " + ", ".join(f"{l['task_id']} ({', '.join(l['leaked'])})"
                                                                         for l in leaks) if leaks else "")))

    dups = []
    for fam in families:
        fam_tasks = tasks[fam.NAME]
        data_hash = [hashlib.sha1(_key(t["data"]).encode()).hexdigest() for t in fam_tasks]
        sh = [shingles(t["prompt"], DUP_SHINGLE) for t in fam_tasks]
        for i in range(len(fam_tasks)):
            for j in range(i + 1, len(fam_tasks)):
                if data_hash[i] != data_hash[j]:
                    continue
                jac = _jaccard(sh[i], sh[j])
                if jac >= DUP_JACCARD:
                    dups.append({"a": fam_tasks[i]["id"], "b": fam_tasks[j]["id"], "jaccard": round(jac, 3)})
    checks.append(_check("no duplicated tasks", not dups,
                         f"{len(dups)} near-duplicate pairs (same data, prompt {DUP_SHINGLE}-word-shingle Jaccard >= "
                         f"{DUP_JACCARD})" + (": " + ", ".join(f"{d['a']} ~ {d['b']} ({d['jaccard']})" for d in dups)
                                              if dups else "")))

    thin, counts_detail = [], []
    for fam in families:
        counts = Counter(label for t in tasks[fam.NAME] for label in fam.outcome(t))
        counts_detail.append(f"{fam.NAME}: " + ", ".join(f"{o} {counts.get(o, 0)}" for o in fam.OUTCOMES))
        thin += [f"{fam.NAME}/{o}" for o in fam.OUTCOMES if counts.get(o, 0) < MIN_PER_OUTCOME]
    checks.append(_check(f"every outcome appears in at least {MIN_PER_OUTCOME} tasks", not thin,
                         "; ".join(counts_detail)))

    unstable = []
    for name, trajs in runs.items():
        again = {t["task_id"]: t for t in repeat[name]}
        for t in trajs:
            r = again[t["task_id"]]
            if t["reward"] != r["reward"] or _key(t["answer"]) != _key(r["answer"]):
                unstable.append(f"{name} on {t['task_id']}")
    total_runs = sum(len(v) for v in runs.values())
    checks.append(_check("rewards are identical on a repeat run", not unstable,
                         f"{total_runs - len(unstable)} of {total_runs} runs repeat exactly"
                         + (f": {unstable[:5]}" if unstable else "")))

    gate = all(c["status"] == "PASS" for c in checks)
    return {"gate": "PASS" if gate else "FAIL", "checks": checks, "runs": runs,
            "hacks": hacks, "leaks": leaks, "duplicates": dups}
