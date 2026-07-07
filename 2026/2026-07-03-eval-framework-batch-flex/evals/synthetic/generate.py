"""Generate synthetic evaluation questions from the FAQ knowledge base.

This is step 1 of the eval framework: we sample documents from the same FAQ
data the agent searches over, and for each document ask an LLM to produce
several realistic user questions together with a reference answer and the
line span in the source document that supports it.

The output is a dataset we can later feed to the agent and score.

Usage:
    uv run python -m evals.synthetic.generate                 # defaults
    uv run python -m evals.synthetic.generate --num-docs 20 --seed 1

Reference implementation this is adapted from:
    https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/tree/main/documentation-agent/evals/synthetic
"""

import argparse
import asyncio
import os
import random
import sys
from pathlib import Path
from typing import Literal

import pandas as pd
import requests
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from tqdm.asyncio import tqdm

# Make the project-root modules (search.py) importable whether this file is
# run as a module (`-m evals.synthetic.generate`) or as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from search import COURSE, FAQ_URL  # noqa: E402

MODEL_NAME = "gpt-5.4-mini"
QUESTIONS_PER_DOC = 5
DEFAULT_NUM_DOCS = 10
MAX_CONCURRENCY = 5
DATA_DIR = Path(__file__).parent / "data"


# ── Output schema ────────────────────────────────────────────────────────────
class GeneratedQuestion(BaseModel):
    user_question: str = Field(description="the question we generate")
    reference_answer: str = Field(
        description="the correct answer based on the document we analyzed"
    )
    line_number_start: int = Field(
        description="the line in the source document where the reference answer starts"
    )
    line_number_end: int = Field(
        description="the line in the source document where the reference answer ends"
    )
    question_type: Literal[
        "stuck_participant",
        "course_logistics",
    ] = Field(description="the persona style used to phrase the question")


class QuestionsResponse(BaseModel):
    questions: list[GeneratedQuestion]


# ── Prompts ──────────────────────────────────────────────────────────────────
INSTRUCTIONS = """
You are an expert at generating realistic user questions based on a course FAQ.
Your task is to analyze the provided FAQ entry and generate questions that a
student might realistically ask.

We want questions that represent REAL students who are stuck, frustrated, or
searching for specific information — rather than perfectly phrased textbook
questions.

Our users are participants of the course. Pick whichever of the two personas
below best fits the FAQ entry:
1. stuck_participant: A student going through the course materials who hit a
   problem while doing a module and describes what they were trying to do.
   (e.g. "kafka python throwing module not found, what am I missing?")
2. course_logistics: A student asking about how the course is organized —
   start dates, deadlines, prerequisites, homework submission, certificates,
   registration. (e.g. "did I miss the deadline to still get a certificate?")

For each generated question, extract the reference answer directly from the
document's content, and pinpoint the exact starting and ending line numbers in
the provided (line-numbered) document where this answer is located.

Follow these strict guidelines:
1. DO NOT end questions with phrases like "based on this text" or "according to
   the documentation."
2. DO NOT make the questions too formal or academic.
3. The reference answer should be comprehensive and directly supported by the text.
4. The line numbers must accurately reflect where the reference answer is found.
""".strip()

PROMPT_TEMPLATE = """
Number of questions to generate:
{number_of_questions}

FAQ section: {section}
FAQ question: {question}

Document (the answer, with line numbers):
{numbered_content}
""".strip()


def add_line_numbers(document: str) -> str:
    lines = document.splitlines()
    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines))


def create_user_prompt(doc: dict, number_of_questions: int) -> str:
    return PROMPT_TEMPLATE.format(
        number_of_questions=number_of_questions,
        section=doc.get("section", ""),
        question=doc.get("question", ""),
        numbered_content=add_line_numbers(doc["answer"]),
    )


# ── Data loading & sampling ──────────────────────────────────────────────────
def load_documents() -> list[dict]:
    documents = requests.get(FAQ_URL).json()
    return [d for d in documents if d.get("course") == COURSE and d.get("answer")]


def sample_documents(documents: list[dict], num_docs: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    if num_docs >= len(documents):
        return list(documents)
    return rng.sample(documents, num_docs)


# ── Generation ───────────────────────────────────────────────────────────────
async def generate_for_document(
    client: AsyncOpenAI, doc: dict, num_questions: int, semaphore: asyncio.Semaphore
) -> list[dict]:
    prompt = create_user_prompt(doc, num_questions)
    async with semaphore:
        response = await client.responses.parse(
            model=MODEL_NAME,
            instructions=INSTRUCTIONS,
            input=prompt,
            text_format=QuestionsResponse,
        )

    parsed = response.output_parsed
    if parsed is None:
        return []

    rows = []
    for q in parsed.questions:
        rows.append(
            {
                "question": q.user_question,
                "reference_answer": q.reference_answer,
                "line_number_start": q.line_number_start,
                "line_number_end": q.line_number_end,
                "question_type": q.question_type,
                "doc_id": doc.get("id"),
                "section": doc.get("section"),
                "source_question": doc.get("question"),
            }
        )
    return rows


async def generate(num_docs: int, num_questions: int, seed: int) -> pd.DataFrame:
    documents = load_documents()
    sample = sample_documents(documents, num_docs, seed)
    print(f"Loaded {len(documents)} FAQ docs; sampled {len(sample)} (seed={seed}).")

    client = AsyncOpenAI()
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    tasks = [
        generate_for_document(client, doc, num_questions, semaphore) for doc in sample
    ]
    results = await tqdm.gather(*tasks, desc="Generating questions")

    rows = [row for doc_rows in results for row in doc_rows]
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-docs", type=int, default=DEFAULT_NUM_DOCS,
                        help="how many FAQ documents to sample")
    parser.add_argument("--num-questions", type=int, default=QUESTIONS_PER_DOC,
                        help="questions to generate per document")
    parser.add_argument("--seed", type=int, default=42,
                        help="random seed for sampling (for reproducibility)")
    parser.add_argument("--output", type=str, default="questions_generated",
                        help="output filename stem (written under data/ as .csv and .json)")
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set (put it in .env).")

    df = asyncio.run(generate(args.num_docs, args.num_questions, args.seed))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_DIR / f"{args.output}.csv"
    json_path = DATA_DIR / f"{args.output}.json"
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2)

    print(f"\nGenerated {len(df)} questions.")
    print(f"Saved: {csv_path}")
    print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
