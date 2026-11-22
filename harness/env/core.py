MAX_STEPS = 15


class ToolError(Exception):
    pass


class Episode:
    def __init__(self, task, family):
        self.task = task
        self.family = family
        self.state = None
        self.steps = []
        self.done = False

    def reset(self):
        self.state = self.family.initial_state(self.task)
        self.steps = []
        self.done = False
        return {"task_id": self.task["id"], "family": self.family.NAME, "prompt": self.task["prompt"],
                "spec": self.task["spec"], "tools": self.family.TOOLS}

    def step(self, action):
        if self.done:
            raise RuntimeError("episode is over, call reset() first")
        tool = action.get("tool")
        args = action.get("args") or {}
        if tool == "submit":
            obs = {"ok": True, "result": "submitted"}
            self.done = True
        elif tool not in self.family.TOOLS:
            obs = {"ok": False, "error": f"unknown tool: {tool}"}
        else:
            try:
                obs = {"ok": True, "result": self.family.apply(self.state, tool, args)}
            except ToolError as e:
                obs = {"ok": False, "error": str(e)}
        self.steps.append({"step": len(self.steps) + 1, "tool": tool, "args": args, "obs": obs})
        if len(self.steps) >= MAX_STEPS:
            self.done = True
        return obs, self.done

    def reward(self):
        return self.family.reward(self.task, self.state)

    def answer(self):
        return self.family.final_answer(self.state)


def run_episode(task, family, agent, agent_name):
    ep = Episode(task, family)
    start = ep.reset()
    gen = agent(start)
    try:
        action = next(gen)
        while True:
            obs, done = ep.step(action)
            if done:
                break
            action = gen.send(obs)
    except StopIteration:
        pass
    if not ep.done:
        ep.step({"tool": "submit"})
    trajectory = {"task_id": task["id"], "family": family.NAME, "agent": agent_name,
                  "reward": ep.reward(), "answer": ep.answer(), "steps": ep.steps}
    family.close(ep.state)
    return trajectory
