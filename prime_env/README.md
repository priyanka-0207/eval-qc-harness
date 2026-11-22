# eval-qc-env

The 30 tasks from the eval QC harness RL environment, packaged for Prime Intellect's `verifiers` library and Environments Hub.

## Status

Written against the `verifiers.v1` API as documented on the library's main branch (`docs/tasksets.md` and `docs/building-environments.md`, read Nov 19 2026). It has **not been run with `verifiers` yet**: the library isn't installed on this machine, so the steps under "Check it" are still to do.

What is tested offline (`tests/test_prime_env.py` in the harness):

- The bridge loads the same 30 tasks as the harness.
- The reference solution scores 1.0 and an empty attempt scores 0.0 on every task through the bridge.
- The bridge reward equals the harness reward for both baseline agents on every task.
- The prompt an agent sees lists the tools and the spec, and never contains the answer.
- The vendored copy of the harness code matches the harness byte for byte.

## How it maps

| Harness | verifiers |
|---|---|
| A task family's tools | A per-rollout `vf.Toolset`, one per family (`support_*`, `warehouse_*`, `helpcenter_*`), served over MCP |
| Episode state (orders, read-only SQLite, search index) | Kept on the tool server for the rollout |
| What the reward needs (refunds, escalations, replies, flagged rows, the answer) | Copied into `trace.state.record` after every tool call |
| The code reward | One `@vf.reward` method, `verified`, that calls the same reward function as the harness |
| The reference solution | `Task.validate`, so `vf-validate` checks that the gold answer scores 1.0 |

Answers stay in the task's `task_json` field. verifiers keeps extra `TaskData` fields on the evaluator and doesn't put them in the prompt. The tool server can see them, but no tool returns them.

## Layout

```
prime_env/
  pyproject.toml
  sync_vendor.py                 copies harness/env code into eval_qc_env/_vendor
  eval_qc_env/
    __init__.py                  exports EvalQCTaskset
    taskset.py                   TaskData, Task classes, Taskset, reward, validate
    bridge.py                    plain Python glue, no verifiers import
    state.py                     EvalQCState
    servers/                     one Toolset module per family
    _vendor/                     copy of harness bm25, text and env modules
```

The harness has no package install, so `sync_vendor.py` copies the six modules the tasks need. Run it after any change to `harness/env/`, and `python prime_env/sync_vendor.py --check` fails when the copy is stale.

## Check it

Needs Python 3.11 or newer, `uv`, and the Prime CLI:

```bash
uv tool install prime
uv pip install -e prime_env
uv run vf-validate eval-qc-env -n 3
```

`vf-validate` should report the gold answer at 1.0 and an untouched task at 0.0. Then one real rollout with a model and an MCP-capable harness:

```bash
uv run vf-run eval-qc-env -n 3 -r 1
```

Pick a single family with `--env.taskset.family tickets` (or `dataqc`, `retrieval`).

## Publish it

```bash
prime env push --path prime_env
```

This needs a Prime Intellect account. I didn't check whether the Hub requires anything beyond that, or whether the push command has changed in the newest CLI.

## Things to confirm on the first real run

- A `Taskset` typed on `EvalQCTask` holding the three `EvalQCTask` subclasses.
- `setup_task` receiving the rollout's `TaskData` with `task_json` on it.
- `record: dict = {}` on `vf.State` syncing back after each tool call.
- Tool docstrings are kept on purpose: verifiers uses them as the tool descriptions.
