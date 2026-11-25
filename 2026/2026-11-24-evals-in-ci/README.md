# Evals in CI

Code from the AI Shipping Labs workshop "Evals in CI" (November 24, 2026).

The base is the FAQ agent and eval pipeline from
[Using Jev for LLM Evaluations](https://github.com/AI-Shipping-Labs/workshops/tree/main/2026/2026-09-22-using-jev-for-llm-evaluations).
I kept only the OpenAI baseline judge and removed the Jev and Laya judges.

## What's here

- `agent.py`, `search.py`, `renderer.py`, `cli.py`: the FAQ agent. It uses the
  OpenAI Responses API with one `search` tool over the DE Zoomcamp FAQ (`minsearch`).
- `evals/synthetic/run.py`: runs the agent over `questions_sample.csv` (50 questions)
  and saves answers plus tool trajectories to `evals_run_*.json`.
- `evals/synthetic/judge.py` and `run_judge.py`: an LLM judge (`gpt-5.4-mini`) with
  three good/bad checks: correctness, instruction following and trajectory. It writes
  `*_judged.json` and a Markdown/JSON report with the cost.
- `evals/synthetic/data/evals_run_sample.json`: a recorded 10-entry run. You can try
  the judge on it without running the agent.

## Setup

```bash
uv sync
cp env.example .env   # put OPENAI_API_KEY in .env
uv run python cli.py "How do I install Kafka?"
uv run python -m evals.synthetic.run --limit 5 --concurrency 3
uv run python -m evals.synthetic.run_judge --data evals/synthetic/data/evals_run_sample.json
```

## Tests and CI

```bash
uv run pytest -v
```

- `tests/test_search.py`: offline checks on the FAQ search. These don't need an API key.
- `tests/test_agent.py`: one real agent run (one question). It checks that the agent
  calls `search`, that the answer ends with a `Sources` section, and that the cited
  ids come from the search results. Locally these tests skip without
  `OPENAI_API_KEY`. In CI they fail without it.
- `.github/workflows/tests.yml` runs the suite on pushes to `main` that change code
  (`*.py`, `pyproject.toml`, `uv.lock`, `.python-version` or the workflow itself),
  and on manual dispatch. Docs-only pushes don't run it. It needs an `OPENAI_API_KEY` repository secret.
- The job runs on a self-hosted runner (`runs-on: [self-hosted, hetzner]`), not on
  GitHub-hosted machines. The workflow sets `UV_EXCLUDE_NEWER: "7 days"` to match the
  global uv config that `uv.lock` was created with. Without it, `uv sync --locked`
  fails on the runner.

## Evals on pull requests

`.github/workflows/evals.yml` runs when you add the `run-evals` label to a PR to `main`.
It doesn't run on other PRs or pushes. When it finishes, it removes the label, so to
re-run on newer commits you add the label again:

```bash
gh pr edit <number> --add-label run-evals
```

What it does:

1. It checks out the PR branch and the baseline, which is the `main` commit the
   branch started from (`git merge-base`).
2. Both versions run the same 20 questions (`EVAL_LIMIT`, seed 42). The eval harness,
   judge and questions come from the PR for both runs, so only the agent code differs.
3. `evals/ci/compare.py` builds a table with the pass rate per check (correctness,
   instruction following, trajectory) for baseline vs feature. It ends with a verdict:
   - ❌ don't merge: any check drops by more than 10 pp, or there are more agent errors
   - ✅ merge: something improved by more than 10 pp and nothing regressed
   - ✅ OK to merge: no significant change

   The table is posted as a PR comment, which is updated on each labeled eval run, and added to
   the job summary. On a regression the job fails.
4. The raw judged results are uploaded as the `eval-results` artifact.

### Cost

- `pricing.py` holds the standard-tier price of every OpenAI text model, taken from
  https://developers.openai.com/api/docs/pricing (checked 2026-11-24).
  Cost is computed per request, because requests over 272K input tokens use the
  long-context rates.
- The eval runner wraps the OpenAI client and records the tokens and cost of every
  agent call (`agent_usage` in the run JSON). This doesn't need changes to `agent.py`,
  so it also works for the baseline. The judge stores `cost_usd` for each check.
- If the agent's or the judge's model isn't in `PRICES`, the eval scripts stop before
  making any API calls, and `tests/test_pricing.py` fails. To switch to a new model,
  add its price first.
- The PR comment has a cost table: the agent model, the agent cost per question and in
  total, and the judge cost. The verdict takes cost into account. A change counts when
  it's larger than ±10%:
  - ⚠️ your call: quality improves, but the agent costs more
  - ❌ don't merge: same quality, but more expensive
  - ✅ merge: same quality, cheaper

Cost per run: 2 × (20 agent runs + 60 judge calls).

Try the comparison locally on two judged files:

```bash
uv run python -m evals.ci.compare --base base_judged.json --feature feature_judged.json
```

## Using this folder

Run the commands above from this folder. To activate GitHub Actions in your own
repository, put these files at that repository's root, including `.github/workflows/`.
Workflows nested in this workshop collection aren't discovered by GitHub Actions.
Replace `runs-on: [self-hosted, hetzner]` with `runs-on: ubuntu-latest` in both
workflow files unless you have a runner with those labels. Add an
`OPENAI_API_KEY` repository secret under Settings > Secrets and variables > Actions.
Create the `run-evals` label in your repository before adding it to a pull request.
The workflow fails on regressions; requiring that check before merging is a
separate repository branch-protection setting.

## Source

Copied from [the workshop repository](https://github.com/alexeygrigorev/evals-workshop)
at commit `ea9bb45` (November 24, 2026). The original pull requests preserve the
[prompt experiment](https://github.com/alexeygrigorev/evals-workshop/pull/1) and
[model experiment](https://github.com/alexeygrigorev/evals-workshop/pull/2), including
their measured results. No API keys or generated private eval runs are included.
