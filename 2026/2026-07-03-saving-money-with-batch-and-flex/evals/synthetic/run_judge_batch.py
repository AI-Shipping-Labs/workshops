"""Run the LLM judge checks over an eval run, via the OpenAI Batch API (~50% cheaper).

Judging is a bunch of independent one-shot LLM calls (unlike the agent run, which
is a live tool-calling loop), so it batches cleanly. For every entry in an
`evals_run_*.json` file we submit two requests — answer correctness and trajectory
optimality — bundled into one Batch job.

Because Batch is asynchronous, this has subcommands (like generate_batch.py):

    # one shot: submit, poll until done, then download + save the judged file
    uv run python -m evals.synthetic.run_judge_batch run --data evals/synthetic/data/evals_run_sample.json

    # or drive the phases yourself
    uv run python -m evals.synthetic.run_judge_batch submit --data <run.json>
    uv run python -m evals.synthetic.run_judge_batch status --data <run.json>
    uv run python -m evals.synthetic.run_judge_batch fetch  --data <run.json>

Output: <input>_judged.json, with each entry enriched with `judge_answer_correctness`
and `judge_trajectory`.

Reference: https://developers.openai.com/api/docs/guides/batch?lang=python
"""

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from evals.synthetic.judge import CHECKS, JUDGE_MODEL

ENDPOINT = "/v1/responses"
COMPLETION_WINDOW = "24h"
POLL_SECONDS = 15
TERMINAL_STATES = {"completed", "failed", "expired", "cancelled"}
CHECKS_BY_NAME = {c["name"]: c for c in CHECKS}


def load_entries(data_path: Path, limit: int | None) -> list[dict]:
    entries = json.loads(data_path.read_text())
    return entries[:limit] if limit is not None else entries


def state_path(data_path: Path) -> Path:
    return data_path.with_name(data_path.stem + ".judge_batch.json")


def custom_id(index: int, check_name: str) -> str:
    return f"{index}__{check_name}"


def parse_custom_id(cid: str) -> tuple[int, str]:
    index, check_name = cid.split("__", 1)
    return int(index), check_name


def build_request(index: int, entry: dict, check: dict) -> dict:
    return {
        "custom_id": custom_id(index, check["name"]),
        "method": "POST",
        "url": ENDPOINT,
        "body": {
            "model": JUDGE_MODEL,
            "instructions": check["instructions"],
            "input": check["format"](entry),
            "text": {"format": check["text_format"]},
        },
    }


# ── submit ───────────────────────────────────────────────────────────────────
def submit(client: OpenAI, args) -> dict:
    data_path = Path(args.data)
    entries = load_entries(data_path, args.limit)
    print(f"Loaded {len(entries)} entries from {data_path}"
          + (f" (limit {args.limit})" if args.limit is not None else "") + ".")

    input_path = data_path.with_name(data_path.stem + ".judge_batch_input.jsonl")
    with open(input_path, "w") as f:
        for i, entry in enumerate(entries):
            for check in CHECKS:
                f.write(json.dumps(build_request(i, entry, check)) + "\n")
    num_requests = len(entries) * len(CHECKS)
    print(f"Wrote {num_requests} requests ({len(entries)} entries x {len(CHECKS)} checks) to {input_path}")

    batch_input_file = client.files.create(file=open(input_path, "rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=batch_input_file.id,
        endpoint=ENDPOINT,
        completion_window=COMPLETION_WINDOW,
        metadata={"description": "FAQ agent judge checks"},
    )

    state = {
        "batch_id": batch.id,
        "input_file_id": batch_input_file.id,
        "data_path": str(data_path),
        "limit": args.limit,
        "model": JUDGE_MODEL,
        "num_entries": len(entries),
        "num_requests": num_requests,
    }
    state_path(data_path).write_text(json.dumps(state, indent=2))
    print(f"Submitted batch {batch.id} (status: {batch.status}).")
    print(f"State saved to {state_path(data_path)}")
    return state


# ── status ───────────────────────────────────────────────────────────────────
def load_state(args) -> dict:
    if args.batch_id:
        return {"batch_id": args.batch_id, "data_path": args.data, "limit": args.limit}
    path = state_path(Path(args.data))
    if not path.exists():
        raise SystemExit(f"No batch state at {path}. Pass --batch-id or run `submit` first.")
    return json.loads(path.read_text())


def status(client: OpenAI, args):
    state = load_state(args)
    batch = client.batches.retrieve(state["batch_id"])
    counts = batch.request_counts
    print(f"Batch {batch.id}: {batch.status}")
    if counts:
        print(f"  requests: total={counts.total} completed={counts.completed} failed={counts.failed}")
    return batch


# ── fetch ────────────────────────────────────────────────────────────────────
def extract_output_text(body: dict) -> str:
    parts = []
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "".join(parts)


def fetch(client: OpenAI, args) -> None:
    state = load_state(args)
    batch = client.batches.retrieve(state["batch_id"])
    if batch.status != "completed":
        raise SystemExit(f"Batch {batch.id} is '{batch.status}', not completed yet.")

    data_path = Path(state["data_path"])
    entries = load_entries(data_path, state.get("limit"))

    output = client.files.content(batch.output_file_id).text
    failures = 0
    for line in output.strip().split("\n"):
        if not line:
            continue
        result = json.loads(line)
        index, check_name = parse_custom_id(result["custom_id"])
        check = CHECKS_BY_NAME[check_name]
        response = result.get("response") or {}
        if response.get("status_code") != 200:
            failures += 1
            entries[index][check["result_key"]] = {
                "reasoning": f"Error: {result.get('error') or response.get('status_code')}",
                "score": "bad",
            }
            continue
        text = extract_output_text(response["body"])
        parsed = check["model"].model_validate_json(text)
        entries[index][check["result_key"]] = parsed.model_dump()

    if batch.error_file_id:
        errors = client.files.content(batch.error_file_id).text.strip()
        if errors:
            print("Error file contents:")
            print(errors)

    output_path = data_path.with_name(data_path.stem + "_judged.json")
    output_path.write_text(json.dumps(entries, indent=2, default=str))
    print(f"\nSaved judged results to {output_path} ({failures} requests failed).")
    report(entries)


def report(entries: list[dict]) -> None:
    total = len(entries)
    print("\n" + "=" * 55)
    print("  JUDGE CHECK RESULTS")
    print("=" * 55)
    print(f"  Total entries evaluated : {total}")
    print("-" * 55)
    for check in CHECKS:
        key = check["result_key"]
        good = sum(1 for e in entries if e.get(key, {}).get("score") == "good")
        pct = (good / total * 100) if total else 0
        print(f"  {check['name']:<22s}  good: {good}  bad: {total - good}  ({pct:.0f}% good)")
    print("=" * 55)


# ── run (submit + poll + fetch) ──────────────────────────────────────────────
def run(client: OpenAI, args) -> None:
    submit(client, args)
    print(f"\nPolling every {POLL_SECONDS}s until the batch finishes...")
    while True:
        batch = status(client, args)
        if batch.status in TERMINAL_STATES:
            break
        time.sleep(POLL_SECONDS)
    if batch.status != "completed":
        raise SystemExit(f"Batch ended in state '{batch.status}'; nothing to fetch.")
    fetch(client, args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("submit", "run"):
        p = sub.add_parser(name)
        p.add_argument("--data", required=True, help="Path to an evals_run_*.json file.")
        p.add_argument("--limit", type=int, default=None, help="Only judge the first N entries.")
        p.add_argument("--batch-id", type=str, default=None)

    for name in ("status", "fetch"):
        p = sub.add_parser(name)
        p.add_argument("--data", required=True, help="Path to the evals_run_*.json file used at submit.")
        p.add_argument("--limit", type=int, default=None)
        p.add_argument("--batch-id", type=str, default=None)

    args = parser.parse_args()
    load_dotenv()
    client = OpenAI()

    {"submit": submit, "status": status, "fetch": fetch, "run": run}[args.command](client, args)


if __name__ == "__main__":
    main()
