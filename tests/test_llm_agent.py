from harness.env import dataqc, retrieval, tickets
from harness.env import run as env_run
from harness.env.core import run_episode
from harness.env.llm_agent import make_agent, tool_schemas
from harness.env.llm_run import summarize


class ScriptedClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def chat(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        return self.replies.pop(0)


def call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def test_tool_schemas_types():
    schemas = {s["function"]["name"]: s["function"]["parameters"] for s in tool_schemas(dataqc.TOOLS)}
    assert schemas["flag"]["properties"]["row_ids"]["type"] == "array"
    assert schemas["run_sql"]["required"] == ["query"]
    assert "submit" in schemas
    refund = {s["function"]["name"]: s["function"]["parameters"] for s in tool_schemas(tickets.TOOLS)}["issue_refund"]
    assert refund["properties"]["amount"]["type"] == "number" and refund["required"] == ["order_id", "amount"]
    answer = {s["function"]["name"]: s["function"]["parameters"] for s in tool_schemas(retrieval.TOOLS)}["answer"]
    assert answer["required"] == ["doc_id", "value", "quote"]


def test_model_tool_calls_drive_the_episode_and_get_the_code_reward():
    task = env_run.build_tasks()["tickets"][0]
    target = task["hidden"]
    client = ScriptedClient([
        call("list_orders", customer_id="C-104"),
        call("issue_refund", order_id=target["order_id"], amount=target["amount"]),
        call("submit"),
    ])
    traj = run_episode(task, tickets, make_agent(client), "fake")
    assert [s["tool"] for s in traj["steps"]] == ["list_orders", "issue_refund", "submit"]
    assert traj["reward"] == 1
    last = client.seen[-1]
    assert last[-1]["role"] == "tool" and "refund" in last[-1]["content"].lower()


def test_model_that_never_calls_a_tool_is_submitted_with_zero_reward():
    task = env_run.build_tasks()["tickets"][0]
    talk = {"role": "assistant", "content": "I would refund it.", "tool_calls": []}
    traj = run_episode(task, tickets, make_agent(ScriptedClient([talk, talk, talk])), "fake")
    assert [s["tool"] for s in traj["steps"]] == ["submit"]
    assert traj["reward"] == 0


def test_summary_flags_rewarded_wrong_answers():
    trajs = [
        {"task_id": "a", "family": "tickets", "reward": 1, "matches_reference": False, "tool_errors": 0,
         "steps": [{"tool": "submit"}]},
        {"task_id": "b", "family": "tickets", "reward": 0, "matches_reference": False, "tool_errors": 2,
         "steps": [{"tool": "x"}, {"tool": "submit"}]},
    ]
    s = summarize(trajs, ["tickets"])
    assert s["all"] == {"passed": 1, "tasks": 2}
    assert s["rewarded_wrong_answers"] == ["a"] and s["tool_errors"] == 2
