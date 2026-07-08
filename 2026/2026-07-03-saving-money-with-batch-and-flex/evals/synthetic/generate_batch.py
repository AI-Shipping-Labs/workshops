"""Generate synthetic questions via the OpenAI Batch API (≈50% cheaper).

Same generation as `generate.py`, but instead of firing one live request per
document we bundle every document into a single Batch job. The Batch API runs
asynchronously (within a 24h window) and costs about half as much.

Because it's asynchronous, this script has subcommands:

    # one shot: submit, poll until done, then download + save
    uv run python -m evals.synthetic.generate_batch run --num-docs 10

    # or drive the three phases yourself
    uv run python -m evals.synthetic.generate_batch submit --num-docs 10
    uv run python -m evals.synthetic.generate_batch status
    uv run python -m evals.synthetic.generate_batch fetch

State (the batch id + what we sampled) is saved to
`data/<output>.batch.json` so `status`/`fetch` can find the job later.

Reference: https://developers.openai.com/api/docs/guides/batch?lang=python
"""

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema

from evals.synthetic.generate import (
    DATA_DIR,
    DEFAULT_NUM_DOCS,
    INSTRUCTIONS,
    MODEL_NAME,
    QUESTIONS_PER_DOC,
    QuestionsResponse,
    create_user_prompt,
    load_documents,
    sample_documents,
)

ENDPOINT = "/v1/responses"
COMPLETION_WINDOW = "24h"
POLL_SECONDS = 15
TERMINAL_STATES = {"completed", "failed", "expired", "cancelled"}

# Strict JSON schema for the Responses `text.format` field (the batch body
# can't use the SDK `.parse()` helper, so we build the schema ourselves).
STRICT_SCHEMA = to_strict_json_schema(QuestionsResponse)
TEXT_FORMAT = {
    "type": "json_schema",
    "name": "QuestionsResponse",
    "schema": STRICT_SCHEMA,
    "strict": True,
}


def state_path(output: str) -> Path:
    return DATA_DIR / f"{output}.batch.json"


def build_request(doc: dict, num_questions: int) -> dict:
    """One JSONL line for the batch input file."""
    return {
        "custom_id": doc["id"],
        "method": "POST",
        "url": ENDPOINT,
        "body": {
            "model": MODEL_NAME,
            "instructions": INSTRUCTIONS,
            "input": create_user_prompt(doc, num_questions),
            "text": {"format": TEXT_FORMAT},
        },
    }


# ── submit ───────────────────────────────────────────────────────────────────
def submit(client: OpenAI, args) -> dict:
    documents = load_documents()
    sample = sample_documents(documents, args.num_docs, args.seed)
    print(f"Loaded {len(documents)} FAQ docs; sampled {len(sample)} (seed={args.seed}).")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    input_path = DATA_DIR / f"{args.output}.batch_input.jsonl"
    with open(input_path, "w") as f:
        for doc in sample:
            f.write(json.dumps(build_request(doc, args.num_questions)) + "\n")
    print(f"Wrote {len(sample)} requests to {input_path}")

    batch_input_file = client.files.create(file=open(input_path, "rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=batch_input_file.id,
        endpoint=ENDPOINT,
        completion_window=COMPLETION_WINDOW,
        metadata={"description": "synthetic FAQ eval questions"},
    )

    state = {
        "batch_id": batch.id,
        "input_file_id": batch_input_file.id,
        "model": MODEL_NAME,
        "num_questions": args.num_questions,
        "num_docs": len(sample),
        "output": args.output,
    }
    state_path(args.output).write_text(json.dumps(state, indent=2))
    print(f"Submitted batch {batch.id} (status: {batch.status}).")
    print(f"State saved to {state_path(args.output)}")
    return state


# ── status ───────────────────────────────────────────────────────────────────
def load_state(args) -> dict:
    if args.batch_id:
        return {"batch_id": args.batch_id, "output": args.output}
    path = state_path(args.output)
    if not path.exists():
        raise SystemExit(f"No batch state at {path}. Pass --batch-id or run `submit` first.")
    return json.loads(path.read_text())


def status(client: OpenAI, args) -> "object":
    state = load_state(args)
    batch = client.batches.retrieve(state["batch_id"])
    counts = batch.request_counts
    print(f"Batch {batch.id}: {batch.status}")
    if counts:
        print(f"  requests: total={counts.total} completed={counts.completed} failed={counts.failed}")
    return batch


# ── fetch ────────────────────────────────────────────────────────────────────
def extract_output_text(body: dict) -> str:
    """Pull the assistant text out of a raw Responses API body."""
    parts = []
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "".join(parts)


def fetch(client: OpenAI, args) -> None:
    import pandas as pd

    state = load_state(args)
    batch = client.batches.retrieve(state["batch_id"])
    if batch.status != "completed":
        raise SystemExit(f"Batch {batch.id} is '{batch.status}', not completed yet.")

    docs_by_id = {d["id"]: d for d in load_documents()}

    output = client.files.content(batch.output_file_id).text
    rows, failures = [], 0
    for line in output.strip().split("\n"):
        if not line:
            continue
        result = json.loads(line)
        doc_id = result["custom_id"]
        response = result.get("response") or {}
        if response.get("status_code") != 200:
            failures += 1
            print(f"  request {doc_id} failed: {result.get('error') or response.get('status_code')}")
            continue

        text = extract_output_text(response["body"])
        parsed = QuestionsResponse.model_validate_json(text)
        doc = docs_by_id.get(doc_id, {})
        for q in parsed.questions:
            rows.append({
                "question": q.user_question,
                "reference_answer": q.reference_answer,
                "line_number_start": q.line_number_start,
                "line_number_end": q.line_number_end,
                "question_type": q.question_type,
                "doc_id": doc_id,
                "section": doc.get("section"),
                "source_question": doc.get("question"),
            })

    # Surface any request-level errors from the batch error file.
    if batch.error_file_id:
        errors = client.files.content(batch.error_file_id).text.strip()
        if errors:
            print("Error file contents:")
            print(errors)

    df = pd.DataFrame(rows)
    stem = state.get("output", args.output)
    csv_path = DATA_DIR / f"{stem}.csv"
    json_path = DATA_DIR / f"{stem}.json"
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2)

    print(f"\nGenerated {len(df)} questions ({failures} requests failed).")
    print(f"Saved: {csv_path}")
    print(f"Saved: {json_path}")


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

    def add_gen_args(p):
        p.add_argument("--num-docs", type=int, default=DEFAULT_NUM_DOCS)
        p.add_argument("--num-questions", type=int, default=QUESTIONS_PER_DOC)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--output", type=str, default="questions_generated")

    p_submit = sub.add_parser("submit", help="build + upload + create the batch job")
    add_gen_args(p_submit)

    p_status = sub.add_parser("status", help="check batch status")
    p_status.add_argument("--output", type=str, default="questions_generated")
    p_status.add_argument("--batch-id", type=str, default=None)

    p_fetch = sub.add_parser("fetch", help="download results and save the dataset")
    p_fetch.add_argument("--output", type=str, default="questions_generated")
    p_fetch.add_argument("--batch-id", type=str, default=None)

    p_run = sub.add_parser("run", help="submit, poll until done, then fetch")
    add_gen_args(p_run)
    p_run.add_argument("--batch-id", type=str, default=None)

    args = parser.parse_args()
    load_dotenv()
    client = OpenAI()

    {"submit": submit, "status": status, "fetch": fetch, "run": run}[args.command](client, args)


if __name__ == "__main__":
    main()
