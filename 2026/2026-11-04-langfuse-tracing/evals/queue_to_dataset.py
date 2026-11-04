"""Promote annotated traces from an annotation queue to a dataset.

Flow: traces -> review queue (human scores/corrections in UI) -> dataset items.
Only COMPLETED queue items with an `answer_correct` score are promoted:
  - scored correct  -> expected_output = {answer: observed_answer}
  - has correction  -> expected_output = {answer: correction text}
  - unscored        -> skipped

Traces already linked to the dataset (by source_trace_id) are skipped.

Usage:
    uv run python queue_to_dataset.py --queue faq-review --dataset faq-eval-v1 --dry-run
    uv run python queue_to_dataset.py --queue faq-review --dataset faq-eval-v1
"""

from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv
from langfuse import get_client

FIELDS = "core,basic,io,model,usage,metrics"
SCORE_NAME = "answer_correct"


def _maybe_parse(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def parse_question(raw_input) -> str | None:
    # run_agent(client, question, renderer) traces all args; the question is
    # args[1]. Only the question string is extracted, never the client blob.
    data = _maybe_parse(raw_input)
    if data is None:
        return None
    if isinstance(data, dict):
        if "args" in data and isinstance(data["args"], list) and len(data["args"]) > 1:
            q = data["args"][1]
            if isinstance(q, str) and q.strip():
                return q.strip()
        kwargs = data.get("kwargs")
        if isinstance(kwargs, dict) and isinstance(kwargs.get("question"), str):
            return kwargs["question"].strip() or None
        if isinstance(data.get("question"), str):
            return data["question"].strip() or None
    if isinstance(data, str):
        return data.strip() or None
    return None


def parse_answer(raw_output) -> str | None:
    if raw_output is None:
        return None
    if not isinstance(raw_output, str):
        return str(raw_output).strip() or None
    text = raw_output.strip()
    if not text:
        return None
    try:
        decoded = json.loads(text)
        if isinstance(decoded, str) and decoded.strip():
            return decoded.strip()
    except (json.JSONDecodeError, ValueError):
        pass
    return text


def _tool_calls_from_generation(output) -> list[dict]:
    data = _maybe_parse(output)
    calls: list[dict] = []
    items = [data] if isinstance(data, dict) else (data if isinstance(data, list) else [])
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "function_call" or "arguments" in item:
            args = item.get("arguments", "")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    pass
            calls.append({"name": item.get("name"), "arguments": args})
    return calls


def _hits_from_output(output, limit: int = 5) -> tuple[list[str], int]:
    data = _maybe_parse(output)
    if not isinstance(data, list):
        return [], 0
    ids = [d.get("id") for d in data if isinstance(d, dict) and d.get("id")]
    return ids[:limit], len(data)


def build_trajectory(observations) -> tuple[list[dict], dict]:
    steps: list[dict] = []
    tool_queries: list[str] = []
    retrieved_ids: list[str] = []
    models: list[str] = []
    total_tokens = 0
    for i, o in enumerate(sorted(observations, key=lambda x: str(x.start_time))):
        step: dict = {"n": i, "name": o.name, "type": str(o.type)}
        if getattr(o, "model", None):
            step["model"] = o.model
            models.append(o.model)
        usage = getattr(o, "usage_details", None) or {}
        if isinstance(usage, dict) and usage.get("total"):
            try:
                total_tokens += int(usage["total"])
            except (TypeError, ValueError):
                pass
        if o.type == "GENERATION":
            calls = _tool_calls_from_generation(o.output)
            if calls:
                step["tool_calls"] = calls
                for c in calls:
                    q = (c.get("arguments") or {}).get("query") if isinstance(c.get("arguments"), dict) else None
                    if q:
                        tool_queries.append(q)
        elif o.name in ("tool.search", "retrieval.minsearch"):
            parsed_in = _maybe_parse(o.input)
            q = parsed_in.get("kwargs", {}).get("query") if isinstance(parsed_in, dict) else None
            ids, count = _hits_from_output(o.output)
            if q:
                step["query"] = q
                if o.name == "tool.search":
                    tool_queries.append(q)
            step["hit_ids"] = ids
            step["hit_count"] = count
            retrieved_ids.extend(ids)
        steps.append(step)
    summary = {
        "n_steps": len(steps),
        "n_llm_calls": sum(1 for s in steps if s.get("name") == "OpenAI-generation"),
        "tool_queries": tool_queries,
        "retrieved_ids": list(dict.fromkeys(retrieved_ids))[:10],
        "model": models[0] if models else None,
        "total_tokens": total_tokens or None,
    }
    return steps, summary


def resolve_queue_id(lf, queue_ref: str) -> str:
    queues = lf.api.annotation_queues.list_queues(limit=50)
    for q in queues.data:
        if q.id == queue_ref or q.name == queue_ref:
            return q.id
    raise SystemExit(f"Queue '{queue_ref}' not found.")


def existing_source_traces(lf, dataset_name: str) -> set[str]:
    try:
        lf.get_dataset(dataset_name)
    except Exception:
        return set()
    seen: set[str] = set()
    page = 1
    while True:
        res = lf.api.dataset_items.list(dataset_name=dataset_name, page=page, limit=100)
        for item in res.data:
            if getattr(item, "source_trace_id", None):
                seen.add(item.source_trace_id)
        total = getattr(res.meta, "total_items", len(res.data)) if hasattr(res, "meta") else len(res.data)
        if len(seen) >= total or not res.data:
            break
        page += 1
    return seen


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default="faq-review", help="Queue name or id.")
    parser.add_argument("--dataset", default="faq-eval-v1")
    parser.add_argument("--status", default="COMPLETED", help="Only promote items with this queue status.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lf = get_client()
    lf.auth_check()

    queue_id = resolve_queue_id(lf, args.queue)
    queue_items = lf.api.annotation_queues.list_queue_items(queue_id=queue_id, limit=100)
    trace_ids = [
        i.object_id for i in queue_items.data
        if str(getattr(i.object_type, "value", i.object_type)).upper() == "TRACE"
        and str(getattr(i.status, "value", i.status)).upper() == args.status.upper()
    ]
    print(f"Queue '{args.queue}': {len(trace_ids)} {args.status} trace(s).")

    seen = existing_source_traces(lf, args.dataset)
    if seen:
        print(f"Dataset '{args.dataset}' already links {len(seen)} trace(s), skipping those.")

    if not args.dry_run:
        try:
            lf.get_dataset(args.dataset)
        except Exception:
            lf.create_dataset(name=args.dataset, description="Eval set promoted from annotation queue.")
            print(f"Created dataset '{args.dataset}'.")

    promoted = skipped = 0
    for tid in trace_ids:
        if tid in seen:
            skipped += 1
            continue
        obs = lf.api.observations.get_many(trace_id=tid, limit=100, fields=FIELDS)
        roots = [o for o in obs.data if o.name == "agent.run" and o.is_root_observation]
        if not roots:
            print(f"- trace {tid[:8]}: no agent.run root, skipping")
            skipped += 1
            continue
        root = roots[0]
        question = parse_question(root.input)
        observed = parse_answer(root.output)
        if not question or not observed:
            print(f"- trace {tid[:8]}: unparseable question/answer, skipping")
            skipped += 1
            continue
        scores = list(lf.api.scores.get_many(trace_id=tid).data)
        verdict = next((s for s in scores if s.name == SCORE_NAME), None)
        correction = next((s for s in scores if (s.data_type or "").upper() == "CORRECTION" and s.value), None)
        if correction:
            expected, reason = {"answer": str(correction.value)}, "correction"
        elif verdict is not None and verdict.value in (True, 1, "1", "true"):
            expected, reason = {"answer": observed}, "scored-correct"
        else:
            print(f"- trace {tid[:8]}: unscored, skipping")
            skipped += 1
            continue
        steps, summary = build_trajectory(obs.data)
        if args.dry_run:
            print(f"- trace {tid[:8]}: would create item from {reason} q={question[:60]!r}")
            promoted += 1
            continue
        lf.create_dataset_item(
            dataset_name=args.dataset,
            input={"question": question},
            expected_output=expected,
            metadata={
                "observed_answer": observed,
                "annotated_from": reason,
                "queue": args.queue,
                "trace_name": root.name,
                "start_time": str(root.start_time),
                **{k: v for k, v in summary.items() if v is not None},
                "trajectory": steps,
            },
            source_trace_id=tid,
            source_observation_id=root.id,
        )
        promoted += 1
        print(f"- trace {tid[:8]}: promoted via {reason}")

    print(f"done: promoted={promoted} skipped={skipped}")


if __name__ == "__main__":
    main()
