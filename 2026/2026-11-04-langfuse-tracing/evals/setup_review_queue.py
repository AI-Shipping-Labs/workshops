"""Set up the human-review flow: score config + annotation queue + enqueue traces.

Reproduces Step 2 of EVAL_DATASET.md. Idempotent: existing score configs,
queues, and queue items are reused, never duplicated.

Examples:
    # Enqueue explicit traces:
    uv run python evals/setup_review_queue.py --trace-id <tid1> --trace-id <tid2> --dry-run
    # Enqueue traces linked to a dataset:
    uv run python evals/setup_review_queue.py --from-dataset faq-eval-v1
    # Enqueue N most recent agent.run traces in a time window:
    uv run python evals/setup_review_queue.py --sample 20 --from-start-time 2026-10-01T00:00:00Z

After this, annotate in the UI: Human Annotation -> <queue> -> Process queue.
Then promote: uv run python evals/queue_to_dataset.py --queue <queue> --dataset <dataset>
"""

from __future__ import annotations

import argparse
from datetime import datetime

from dotenv import load_dotenv
from langfuse import get_client

SCORE_NAME = "answer_correct"


def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def get_or_create_score_config(lf, name: str, dry_run: bool):
    page = 1
    while True:
        res = lf.api.score_configs.get(page=page, limit=100)
        for cfg in res.data:
            if cfg.name == name:
                print(f"Score config '{name}': exists ({cfg.id}).")
                return cfg
        total = getattr(res.meta, "total_items", len(res.data)) if hasattr(res, "meta") else len(res.data)
        if not res.data or page * 100 >= total:
            break
        page += 1
    if dry_run:
        print(f"Score config '{name}': would create (dry-run).")
        return None
    try:
        cfg = lf.api.score_configs.create(
            name=name,
            data_type="BOOLEAN",
            description="Is the observed answer correct and grounded in retrieved entries?",
        )
        print(f"Score config '{name}': created ({cfg.id}).")
        return cfg
    except Exception as e:
        raise SystemExit(
            f"Could not create score config '{name}': {e}. "
            "If it already exists, pass its id via --score-config-id."
        )


def get_or_create_queue(lf, queue_name: str, score_config_id: str | None, dry_run: bool):
    queues = lf.api.annotation_queues.list_queues(limit=50)
    for q in queues.data:
        if q.name == queue_name:
            print(f"Queue '{queue_name}': exists ({q.id}).")
            return q
    if dry_run:
        print(f"Queue '{queue_name}': would create (dry-run).")
        return None
    if not score_config_id:
        raise SystemExit("Need --score-config-id to create a new queue.")
    q = lf.api.annotation_queues.create_queue(
        name=queue_name,
        score_config_ids=[score_config_id],
        description="Review bootstrapped answers: correctness + correction.",
    )
    print(f"Queue '{queue_name}': created ({q.id}).")
    return q


def sample_agent_run_traces(lf, limit: int, from_start_time, to_start_time) -> list[str]:
    """Most recent agent.run root traces in window, newest first."""
    rows = lf.api.observations.get_many(
        name="agent.run",
        type="AGENT",
        is_root_observation=True,
        limit=min(limit, 1000),
        fields="core,basic",
        from_start_time=from_start_time,
        to_start_time=to_start_time,
    )
    return [o.trace_id for o in rows.data][:limit]


def dataset_source_traces(lf, dataset_name: str) -> list[str]:
    ds = lf.get_dataset(dataset_name)
    return [it.source_trace_id for it in ds.items if it.source_trace_id]


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--queue", default="faq-review")
    p.add_argument("--score-config-id", default=None)
    p.add_argument("--trace-id", action="append", default=[], help="Repeatable.")
    p.add_argument("--from-dataset", default=None, help="Enqueue this dataset's source traces.")
    p.add_argument("--sample", type=int, default=0, help="Enqueue N most recent agent.run traces.")
    p.add_argument("--from-start-time", default=None)
    p.add_argument("--to-start-time", default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    lf = get_client()
    lf.auth_check()

    cfg = get_or_create_score_config(lf, SCORE_NAME, args.dry_run)
    cfg_id = args.score_config_id or (cfg.id if cfg else None)
    queue = get_or_create_queue(lf, args.queue, cfg_id, args.dry_run)
    queue_id = queue.id if queue else "<new-queue>"

    trace_ids: list[str] = list(dict.fromkeys(args.trace_id))
    if args.from_dataset:
        trace_ids += [t for t in dataset_source_traces(lf, args.from_dataset) if t not in trace_ids]
    if args.sample:
        trace_ids += [
            t for t in sample_agent_run_traces(lf, args.sample, _dt(args.from_start_time), _dt(args.to_start_time))
            if t not in trace_ids
        ]
    if not trace_ids:
        raise SystemExit("No traces given. Use --trace-id, --from-dataset, or --sample.")
    print(f"{len(trace_ids)} trace(s) to enqueue.")

    if queue is None:  # dry-run, queue would be created
        for tid in trace_ids:
            print(f"- {tid}: would enqueue (dry-run)")
        return

    existing = {i.object_id for i in lf.api.annotation_queues.list_queue_items(queue_id=queue_id, limit=100).data}
    added = skipped = 0
    for tid in trace_ids:
        if tid in existing:
            skipped += 1
            continue
        if args.dry_run:
            print(f"- {tid}: would enqueue (dry-run)")
            added += 1
            continue
        lf.api.annotation_queues.create_queue_item(queue_id, object_id=tid, object_type="TRACE")
        added += 1
    print(f"done: enqueued={added} already_present={skipped} queue={queue_id}")


if __name__ == "__main__":
    main()
