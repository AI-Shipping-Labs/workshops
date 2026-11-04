# Eval Dataset from Production Traces

Repeatable flow used in this project: **traces → review queue → dataset**.

## Prerequisites

- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` in `.env`
- Python deps: `uv sync --locked`
- Eval tooling lives in `evals/` and nothing else is needed:
  - `evals/setup_review_queue.py` — Step 2 (score config + queue + enqueue)
  - `evals/annotate_trace.py` — Step 3 via API (verdict + correction + complete)
  - `evals/queue_to_dataset.py` — Step 4 (promote annotations to dataset)

## Step 1 — Capture traces (already instrumented)

`agent.py` traces each request with `@observe(as_type="agent", name="agent.run")`,
LLM calls via Langfuse's `AsyncOpenAI` wrapper, and `tool.search` / `retrieval.minsearch`
as nested observations. No change needed for this flow.

Caveat: `run_agent(client, question, renderer)` traces all args, so the root
`input` contains a serialized OpenAI client plus the question at `input["args"][1]`.
The scripts below extract only `args[1]` and never store the client blob.

## Step 2 — Create score config + review queue + enqueue traces

Three Langfuse concepts, briefly:

- **Score config** — a named label template: what dimension to judge on and what
  shape the judgment takes. Ours is `answer_correct`, type boolean (true/false):
  "is the observed answer correct and grounded?" Without it, annotators would
  type free text and scores couldn't be compared or read back by the script.
- **Review (annotation) queue** — a to-do list of traces assigned to human
  reviewers, all judged against the same score configs. It gives the team one
  shared inbox ("everything in `faq-review` needs a correctness verdict")
  instead of everyone clicking around Tracing.
- **Enqueue traces** — putting specific trace IDs onto that to-do list. Only
  enqueued traces get reviewed, so this is also how you sample (e.g. the 20
  most recent failures) instead of labeling everything.

Reproducible via script (idempotent — safe to re-run):

```bash
# Enqueue traces already linked to a dataset:
uv run python evals/setup_review_queue.py --from-dataset faq-eval-v1 --dry-run
uv run python evals/setup_review_queue.py --from-dataset faq-eval-v1

# Or explicit traces, or sample N most recent agent.run roots:
uv run python evals/setup_review_queue.py --trace-id <tid1> --trace-id <tid2>
uv run python evals/setup_review_queue.py --sample 20 --from-start-time 2026-10-01T00:00:00Z
```

What it does: reuses or creates the `answer_correct` (boolean) score config,
reuses or creates the queue (default `faq-review`), and enqueues the traces,
skipping ones already in the queue.

In this session the queue `faq-review` was set up this way and 3 traces were enqueued.

UI equivalent: Human Annotation → New Queue (attach the score config) →
Tracing → select traces → Actions → Add to queue.

To find candidate traces: Observations table → filter `name = agent.run`,
`isRootObservation = true`, bounded time range.

## Step 3 — Annotate (UI or API)

Human Annotation → `faq-review` → Process queue. Per trace:

- `answer_correct = true/false`
- If wrong, add a **correction** with the right answer

This writes scores attached to the trace. It does not touch any dataset.

API equivalent (this is how the 3rd trace in this session was annotated —
2 via UI, 1 via API):

```bash
uv run python evals/annotate_trace.py --trace-id <tid> --correct \
    --comment "Answer matches cited FAQ entry." --queue faq-review --dry-run
uv run python evals/annotate_trace.py --trace-id <tid> --correct \
    --comment "Answer matches cited FAQ entry." --queue faq-review

# If wrong, record what the answer should have been:
uv run python evals/annotate_trace.py --trace-id <tid> --wrong \
    --correction "The correct answer text..." --queue faq-review
```

What it does: writes the `answer_correct` score linked to the score config
(optionally a `CORRECTION` score), and marks the queue item COMPLETED —
the API behind the UI's "Complete + next". Raw calls are `create_score` +
`annotation_queues.update_queue_item`; see `evals/annotate_trace.py`.

## Step 4 — Promote queue → dataset

```bash
uv run python evals/queue_to_dataset.py --queue faq-review --dataset faq-eval-v1 --dry-run
uv run python evals/queue_to_dataset.py --queue faq-review --dataset faq-eval-v1
```

Rules:

- Only `COMPLETED` queue items are considered
- `correction` present → `expected_output = {answer: correction}`
- `answer_correct = true` → `expected_output = {answer: observed_answer}`
- Unscored → skipped, nothing written
- Traces already linked to the dataset (by `source_trace_id`) → skipped, no duplicates

Resulting item shape:

- `input = {"question": ...}` (prod-like, stable for experiments)
- `expected_output = {"answer": ...}` (reviewed reference only)
- `metadata = {observed_answer, annotated_from, queue, trajectory, tool_queries,
  retrieved_ids, model, total_tokens, ...}` plus `source_trace_id` linkage

## Verification

```bash
# Queue state
# Human Annotation -> faq-review: all items COMPLETED
# Scores on traces: answer_correct x N

# Dataset state
uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from langfuse import get_client
ds = get_client().get_dataset('faq-eval-v1')
print(len(ds.items), 'items')
for it in ds.items:
    print(it.id[:8], '| expected set:', bool(it.expected_output))
"
```

## Next round (new traces)

1. Enqueue new trace IDs to `faq-review`:
   `uv run python evals/setup_review_queue.py --queue faq-review --sample 20 ...`
2. Annotate → mark COMPLETED
3. Re-run `evals/queue_to_dataset.py` (same command; already-promoted traces are skipped)
