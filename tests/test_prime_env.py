import sys
from pathlib import Path

PRIME = Path(__file__).resolve().parent.parent / "prime_env"
sys.path.insert(0, str(PRIME))

import sync_vendor
from eval_qc_env import bridge

from harness.env import run as env_run
from harness.env.core import run_episode


def test_vendored_copy_matches_harness():
    assert sync_vendor.out_of_sync() == []


def test_bridge_loads_the_same_thirty_tasks():
    ids = [t["id"] for t in bridge.load_tasks()]
    assert ids == [t["id"] for fam in env_run.build_tasks().values() for t in fam]
    assert len(bridge.load_tasks("dataqc")) == 10


def test_bridge_reward_matches_harness_reward():
    for fam in env_run.FAMILIES:
        for task in bridge.load_tasks(fam.NAME):
            assert bridge.oracle_score(task) == 1.0
            assert bridge.score(task, {}) == 0.0
            for name in ("v1", "v2"):
                expected = run_episode(task, fam, fam.AGENTS[name], name)["reward"]
                vendored = bridge.FAMILIES[fam.NAME]
                assert bridge.score(task, bridge.replay(task, vendored.AGENTS[name])) == expected


def test_prompt_shows_tools_and_spec_but_not_the_answer():
    for task in bridge.load_tasks():
        prompt = bridge.prompt_for(task).lower()
        assert "tools:" in prompt
        fam = bridge.FAMILIES[task["family"]]
        assert not [s for s in fam.leak_strings(task) if s.lower() in prompt]
