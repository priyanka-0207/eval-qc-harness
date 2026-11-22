import json

from ._vendor.env import dataqc, retrieval, tickets
from ._vendor.env.core import MAX_STEPS, ToolError

FAMILIES = {m.NAME: m for m in (tickets, dataqc, retrieval)}


def load_tasks(family="all"):
    out = []
    for name, fam in FAMILIES.items():
        if family not in ("all", name):
            continue
        out.extend(fam.make_tasks())
    return out


def prompt_for(task):
    fam = FAMILIES[task["family"]]
    lines = [task["prompt"]]
    if task["spec"]:
        lines.append("Spec: " + json.dumps(task["spec"]))
    lines.append("Tools: " + "; ".join(f"{name}: {desc}" for name, desc in fam.TOOLS.items()))
    lines.append("Use the tools to finish the task, then reply DONE.")
    return "\n\n".join(lines)


def new_state(task):
    return FAMILIES[task["family"]].initial_state(task)


def call(task, state, tool, args):
    fam = FAMILIES[task["family"]]
    try:
        result = fam.apply(state, tool, args)
    except ToolError as e:
        return json.dumps({"ok": False, "error": str(e)})
    return json.dumps({"ok": True, "result": result}, default=str)


def record(task, state):
    family = task["family"]
    if family == "tickets":
        return {"refunds": [list(r) for r in state["refunds"]], "escalations": list(state["escalations"]),
                "replies": list(state["replies"])}
    if family == "dataqc":
        return {"flagged": sorted(state["flagged"])}
    return {"answer": state["answer"]}


def score(task, rec):
    family = task["family"]
    rec = rec or {}
    if family == "tickets":
        state = {"refunds": rec.get("refunds", []), "escalations": rec.get("escalations", []),
                 "replies": rec.get("replies", [])}
    elif family == "dataqc":
        state = {"flagged": set(rec.get("flagged", []))}
    else:
        state = {"corpus": {d["doc_id"]: d for d in task["data"]["corpus"]}, "answer": rec.get("answer")}
    return float(FAMILIES[family].reward(task, state))


def replay(task, agent):
    fam = FAMILIES[task["family"]]
    state = new_state(task)
    start = {"task_id": task["id"], "family": task["family"], "prompt": task["prompt"],
             "spec": task["spec"], "tools": fam.TOOLS}
    gen = agent(start)
    steps = 0
    try:
        action = next(gen)
        while action.get("tool") != "submit" and steps < MAX_STEPS:
            obs = json.loads(call(task, state, action["tool"], action.get("args") or {}))
            steps += 1
            action = gen.send(obs)
    except StopIteration:
        pass
    rec = record(task, state)
    fam.close(state)
    return rec


def oracle_score(task):
    return score(task, replay(task, FAMILIES[task["family"]].oracle(task)))
