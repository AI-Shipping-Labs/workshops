"""Annotate a trace via API (same as doing it in Human Annotation UI).

Writes an `answer_correct` score on the trace, optionally a CORRECTION,
and marks the trace's queue item COMPLETED.

Examples:
    uv run python evals/annotate_trace.py --trace-id <tid> --correct --dry-run
    uv run python evals/annotate_trace.py --trace-id <tid> --correct \
        --comment "Matches cited FAQ entry." --queue faq-review
    uv run python evals/annotate_trace.py --trace-id <tid> --wrong \
        --correction "The correct answer text..." --queue faq-review
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv
from langfuse import get_client

SCORE_NAME = "answer_correct"


def resolve_score_config_id(lf, name: str) -> str:
    page = 1
    while True:
        res = lf.api.score_configs.get(page=page, limit=100)
        for cfg in res.data:
            if cfg.name == name:
                return cfg.id
        total = getattr(res.meta, "total_items", len(res.data)) if hasattr(res, "meta") else len(res.data)
        if not res.data or page * 100 >= total:
            break
        page += 1
    raise SystemExit(f"Score config '{name}' not found. Create it via evals/setup_review_queue.py first.")


def resolve_queue_id(lf, queue_ref: str) -> str:
    queues = lf.api.annotation_queues.list_queues(limit=50)
    for q in queues.data:
        if q.id == queue_ref or q.name == queue_ref:
            return q.id
    raise SystemExit(f"Queue '{queue_ref}' not found.")


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trace-id", required=True)
    p.add_argument("--score-name", default=SCORE_NAME)
    verdict = p.add_mutually_exclusive_group(required=True)
    verdict.add_argument("--correct", action="store_true")
    verdict.add_argument("--wrong", action="store_true")
    p.add_argument("--correction", default=None, help="Correct answer text (for --wrong).")
    p.add_argument("--comment", default=None)
    p.add_argument("--queue", default=None, help="Mark this queue's item COMPLETED.")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.wrong and not args.correction:
        print("Warning: --wrong without --correction records no reference answer.")

    lf = get_client()
    lf.auth_check()
    config_id = resolve_score_config_id(lf, args.score_name)

    if args.dry_run:
        print(f"Would score trace {args.trace_id[:8]}: {args.score_name}={args.correct}")
        if args.correction:
            print("Would add CORRECTION score.")
        if args.queue:
            print(f"Would mark queue '{args.queue}' item COMPLETED.")
        return

    lf.create_score(
        name=args.score_name,
        value=1 if args.correct else 0,
        trace_id=args.trace_id,
        data_type="BOOLEAN",
        config_id=config_id,
        comment=args.comment,
    )
    print(f"Scored trace {args.trace_id[:8]}: {args.score_name}={args.correct}")
    if args.correction:
        lf.create_score(
            name=args.score_name,
            value=args.correction,
            trace_id=args.trace_id,
            data_type="CORRECTION",
        )
        print("Added CORRECTION score.")
    if args.queue:
        queue_id = resolve_queue_id(lf, args.queue)
        items = lf.api.annotation_queues.list_queue_items(queue_id=queue_id, limit=100)
        item_id = next((i.id for i in items.data if i.object_id == args.trace_id), None)
        if not item_id:
            raise SystemExit(f"Trace not found in queue '{args.queue}'.")
        lf.api.annotation_queues.update_queue_item(queue_id, item_id=item_id, status="COMPLETED")
        print(f"Queue '{args.queue}' item marked COMPLETED.")


if __name__ == "__main__":
    main()
