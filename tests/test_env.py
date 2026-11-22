import json

import pytest

from harness import config
from harness.env import dataqc, retrieval, taskqc, tickets
from harness.env import run as env_run
from harness.env.core import Episode, run_episode


@pytest.fixture
def tmp_reports(tmp_path):
    config.use_root(tmp_path)
    yield tmp_path
    config.use_root(config.ROOT)


def test_thirty_tasks_in_three_families():
    tasks = env_run.build_tasks()
    assert {k: len(v) for k, v in tasks.items()} == {"tickets": 10, "dataqc": 10, "retrieval": 10}


def test_oracle_solves_and_null_scores_zero():
    tasks = env_run.build_tasks()
    for fam in env_run.FAMILIES:
        for task in tasks[fam.NAME]:
            assert run_episode(task, fam, fam.oracle(task), "oracle")["reward"] == 1
            assert run_episode(task, fam, taskqc.null_agent, "null")["reward"] == 0


def test_clean_gate_passes():
    res = taskqc.run(env_run.FAMILIES, env_run.build_tasks())
    assert res["gate"] == "PASS", [c for c in res["checks"] if c["status"] != "PASS"]


def test_dirty_gate_fails_on_the_three_planted_problems():
    res = taskqc.run(env_run.FAMILIES, env_run.build_tasks(dirty=True))
    failed = {c["check"] for c in res["checks"] if c["status"] == "FAIL"}
    assert failed == {"no shortcut agent is rewarded for a wrong answer",
                      "no task shows its answer in the prompt or spec", "no duplicated tasks"}
    assert [(h["agent"], h["task_id"]) for h in res["hacks"]] == [("flag_all", "dataqc-dirty-lenient")]
    assert [l["task_id"] for l in res["leaks"]] == ["retrieval-dirty-leak"]
    assert [(d["a"], d["b"]) for d in res["duplicates"]] == [("tickets-01", "tickets-dirty-dup")]


def test_run_sql_is_read_only():
    task = dataqc.make_tasks()[0]
    ep = Episode(task, dataqc)
    ep.reset()
    obs, _ = ep.step({"tool": "run_sql", "args": {"query": "DELETE FROM payments"}})
    assert not obs["ok"] and "readonly" in obs["error"].replace(" ", "").lower()
    obs, _ = ep.step({"tool": "run_sql", "args": {"query": "SELECT COUNT(*) FROM payments"}})
    assert obs["result"]["rows"] == [[dataqc.ROWS]]
    dataqc.close(ep.state)


def test_lenient_reward_is_hackable_strict_is_not():
    lenient = next(t for t in dataqc.make_tasks(dirty=True) if t["id"] == "dataqc-dirty-lenient")
    strict = dict(lenient, reward_mode="exact")
    assert run_episode(lenient, dataqc, dataqc.flag_all, "flag_all")["reward"] == 1
    assert run_episode(strict, dataqc, dataqc.flag_all, "flag_all")["reward"] == 0


def test_retrieval_quote_must_be_bounded_and_verbatim():
    task = retrieval.make_tasks()[0]
    h = task["hidden"]
    state = retrieval.initial_state(task)
    doc = state["corpus"][h["doc_id"]]
    cases = [(h["quote"], 1), (doc["text"], 0), (h["quote"].replace("is", "was"), 0), (h["value"], 0)]
    for quote, expected in cases:
        state["answer"] = {"doc_id": h["doc_id"], "value": h["value"], "quote": quote}
        assert retrieval.reward(task, state) == expected, quote


def test_ticket_refund_must_match_order_and_amount():
    task = tickets.make_tasks()[0]
    h = task["hidden"]
    state = tickets.initial_state(task)
    state["refunds"] = [[h["order_id"], h["amount"] - 1]]
    assert tickets.reward(task, state) == 0
    state["refunds"] = [[h["order_id"], h["amount"]]]
    assert tickets.reward(task, state) == 1
    state["escalations"] = ["also escalated"]
    assert tickets.reward(task, state) == 0


def test_run_writes_traces_and_finds_the_boundary_regression(tmp_reports):
    res = env_run.run()
    assert res["gate"]["gate"] == "PASS"
    assert "tickets-03" in res["regression"]["broken"]
    traces = res["out"] / "traces"
    v2 = [json.loads(l) for l in (traces / "v2.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(v2) == 30 and all(t["steps"] and t["steps"][-1]["tool"] == "submit" for t in v2)
    assert (res["out"] / "report.md").exists() and (res["out"] / "results.json").exists()
    assert res["pass_rates"]["oracle"]["all"] == {"passed": 30, "tasks": 30}


def test_env_page_shows_the_three_planted_tasks(tmp_reports):
    from harness.env import page
    env_run.run(dirty=False)
    env_run.run(dirty=True)
    out = page.build(tmp_reports / "site" / "env" / "index.html")
    html = out.read_text(encoding="utf-8")
    assert "Answer leaked in the prompt" in html and "retrieval-dirty-leak" in html
    assert "Reward too lenient" in html and "dataqc-dirty-lenient" in html
    assert "Duplicated task" in html and "tickets-dirty-dup" in html
    assert "<mark>90 days</mark>" in html


def test_env_page_skips_without_both_runs(tmp_reports):
    from harness.env import page
    env_run.run(dirty=False)
    assert page.build(tmp_reports / "site" / "env" / "index.html") is None
