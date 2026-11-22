# Eval QC Harness

A QC gate for eval datasets. It catches leaked, duplicated or broken test cases before they lie to your scorer.

Live: https://priyanka-0207.github.io/eval-qc-harness/

Try it: `git clone https://github.com/priyanka-0207/eval-qc-harness`, then `python run.py --dataset cfpb-200`. Python 3.10+, no installs.

## Status

Prototype. 32 tests pass.

- Real run: 2,000 CFPB complaints from 2025, 200 test cases
- Synthetic run: 1,550 generated complaints with planted problems
- LLM judge (gpt-4o-mini) run on both
- RL environment: 30 tasks, played by scripted agents and by Gemma 4

## Purpose

An eval score depends on the test data and the grader. If test cases leak into the data the agent searches, the score goes up. If the grader can be fooled, the score is wrong. This harness checks both before a score counts.

## Methods Used

- Bronze, silver and gold layers with row counts that must add up
- Time-based split: the corpus is older than the test set
- Near-duplicate detection with 5-word shingles and Jaccard similarity
- BM25 retrieval
- Grader tests with planted mistakes and cheating answers
- LLM-as-a-judge with verbatim evidence, checked with Cohen's kappa
- Case-level regression between agent versions
- RL episodes (`reset`, `step`) with code rewards and a task QC gate
- An open model as the agent through Ollama tool calling

## Technologies

Python 3 and pytest. Optional: the OpenAI API for the judge and Ollama for the open-model agent.

## Required Libraries

Standard library only. `pytest` for tests.

## Project Description

### Agent under test

A retrieval agent reads a complaint and returns a product, an escalate flag and a supporting quote. v1 copies the closest past complaint. v2 votes over the 9 closest. Escalation is required for Servicemember or Older American tags and for fraud or identity-theft issues.

### QC gate

| Check | Fails when |
|---|---|
| Row counts | Raw rows minus every drop doesn't equal clean rows |
| Duplicates | A test case is repeated |
| ID leakage | A test case is also in the search corpus |
| Near-copy leakage | A test case is 80%+ the same as a corpus complaint |
| Time order | The corpus isn't older than the test set |
| Product coverage | A product has fewer than 15 test cases |
| Rule coverage | An escalation rule has fewer than 10 cases |

`--ci` exits 1 when a check fails.

### Results on real CFPB data

| | |
|---|---|
| Rows kept | 1,802 of 2,000 (141 duplicates, 57 too short) |
| Clean split | Passed 7 of 7 checks |
| Random split | Failed 2 of 6: near copies, no time order |
| Leaked test cases | 19 of 200 |
| Agent on leaked cases | 18 of 19 right (95%) |
| Agent on the rest | 57% |
| Caught example | The same identity-theft letter sent to Equifax and Experian, 87% identical |
| v2 vs v1 | Products right 71.5% vs 67.5%. Fixed 21 cases, broke 22 |
| LLM judge | Passed 10 of 20 wrong answers. Kappa 0.45 |

### Results on synthetic data

| | |
|---|---|
| Rows kept | 1,303 of 1,550 |
| Clean split | Passed 7 of 7 checks |
| Random split | Failed 4 of 6 |
| LLM judge | Passed 9 of 20 wrong answers. Gave every answer a 3 (kappa 0) |

### RL environment

30 tasks in 3 families: support tickets, data QC on SQLite and help-center retrieval. Every reward is code. The task QC gate checks that each task is solvable, nothing is free, no shortcut gets paid, no answer leaks and no task repeats. With 3 planted bad tasks, it fails exactly those 3.

| Agent | Tickets | Data QC | Retrieval | All |
|---|---|---|---|---|
| Gemma 4 (8B, local) | 5/10 | 5/10 | 3/10 | 13/30 |
| Scripted v2 | 9/10 | 10/10 | 9/10 | 28/30 |
| Scripted v1 | 4/10 | 1/10 | 4/10 | 9/30 |

Gemma's 7 retrieval misses were right answers written as sentences. The reward is too strict there, and fixing it is next.

`prime_env/` packages the tasks for Prime Intellect's `verifiers`. It hasn't been run there yet.

### Limitations

- CFPB product labels are noisy.
- The complaint agents are baselines, not LLMs.
- The RL tasks are synthetic, and nothing has been trained on them.

## To Use

```bash
python run.py --dataset cfpb-200           # real data
python run.py --dataset synthetic          # planted problems
python run.py --dataset cfpb-200 --judge   # add the LLM judge (EVAL_QC_OPENAI_API_KEY in .env)
python -m harness env                      # RL environment
python -m harness env-llm --model gemma4   # open model as the agent (needs Ollama)
python -m harness publish                  # rebuild docs/ for GitHub Pages
python -m pytest -q                        # tests
```

## Author

Priyanka Bhutada
