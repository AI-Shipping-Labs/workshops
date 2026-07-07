"""LLM judge checks for the FAQ agent eval.

Two checks (both scored good/bad by an LLM):

1. Answer correctness  — does the agent's answer convey the same information as
   the reference answer? The agent's answer may be broader, but it must contain
   the key facts of the reference answer.
2. Trajectory optimality — was the tool-call sequence reasonable, i.e. the agent
   searched enough (but not too much)?

Token note: the trajectory judge is shown only the tool NAMES and their query
arguments — NOT the tool results (the FAQ search hits), which are large and
would blow up the token bill.

Adapted (2 of 3 checks, OpenAI SDK instead of pydantic_ai) from:
    https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/main/documentation-agent/evals/synthetic/judge.py
"""

import json
import sys
from pathlib import Path
from typing import Any, Literal

from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, Field

# Import the agent's real system prompt so the instruction judge sees exactly
# what the agent was told to do.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent import INSTRUCTIONS as AGENT_INSTRUCTIONS  # noqa: E402

JUDGE_MODEL = "gpt-5.4-mini"


# ── Output models ────────────────────────────────────────────────────────────
class CorrectnessResult(BaseModel):
    reasoning: str = Field(
        description="Step-by-step reasoning about whether the agent's answer covers the reference answer."
    )
    score: Literal["good", "bad"] = Field(
        description="'good' if the answer conveys the same information as the reference answer, 'bad' otherwise."
    )


class InstructionFollowingResult(BaseModel):
    reasoning: str = Field(
        description="Step-by-step reasoning about whether the agent followed its instructions."
    )
    score: Literal["good", "bad"] = Field(
        description="'good' if the agent's final answer followed its instructions, 'bad' otherwise."
    )


class TrajectoryResult(BaseModel):
    reasoning: str = Field(
        description="Step-by-step reasoning about the optimality of the tool-call trajectory."
    )
    score: Literal["good", "bad"] = Field(
        description="'good' if the trajectory was reasonably efficient, 'bad' if wasteful or insufficient."
    )
    suggestion: str = Field(
        description="Concrete suggestion for how the agent could search more efficiently, or 'none'."
    )


# ── Check 1: Answer correctness ──────────────────────────────────────────────
CORRECTNESS_INSTRUCTIONS = """
You are an expert evaluator. Decide whether an AI agent's answer conveys the
SAME INFORMATION as the reference answer for the user's question.

Rules:
- The reference answer is the ground truth, extracted from the course FAQ.
- The agent's answer does NOT need to be word-for-word identical. It must
  contain the same key facts / conclusion as the reference answer.
- The agent's answer may be BROADER or add extra correct detail — that is fine,
  as long as it still covers what the reference answer says. Mark it "good".
- If the agent provides a correct equivalent approach to the same problem, that
  also counts as "good".
- Mark "bad" only if the agent's answer is missing the key information from the
  reference answer, contradicts it, or is off-topic / wrong.

Focus on meaning, not textual overlap.
""".strip()

CORRECTNESS_PROMPT = """
User Question:
{question}

Reference Answer (ground truth):
{reference_answer}

Agent's Answer:
{agent_answer}
""".strip()


def format_correctness_prompt(entry: dict[str, Any]) -> str:
    return CORRECTNESS_PROMPT.format(
        question=entry["input"]["question"],
        reference_answer=entry["input"]["reference_answer"],
        agent_answer=entry["rag_response"]["answer"],
    )


# ── Check 2: Instruction following ───────────────────────────────────────────
INSTRUCTION_FOLLOWING_INSTRUCTIONS = """
You are an expert evaluator. You will be given:
1. The system-prompt instructions that were given to a course FAQ agent.
2. The user question.
3. The agent's final answer.

Decide whether the agent's FINAL ANSWER followed its instructions. You are
judging the output only — not the internal search process (you are NOT shown
the search results).

You are also shown the agent's tool-call trajectory (tool names + arguments
only; results omitted) so you can check whether it actually used the tools as
instructed.

Read the instructions and check the answer against their concrete, checkable
rules. In particular:
- The agent was told to use the `search` tool to look things up. The trajectory
  should show at least one `search` call (an answer produced with no search at
  all does not follow the instructions).
- The answer should be grounded in the FAQ knowledge base, not invented. If the
  agent states the answer isn't in the FAQ, that is acceptable behavior.
- The answer must end with a "Sources" section listing the FAQ entries used,
  one per line in the form: `- [id] section > question`.

Mark "good" if the answer follows the instructions — in particular it includes a
properly formatted "Sources" section (unless the agent correctly says the answer
isn't in the FAQ, in which case sources may legitimately be absent).
Mark "bad" if it clearly violates the instructions, e.g. the Sources section is
missing or malformed, or it ignores the prescribed format.
""".strip()

INSTRUCTION_FOLLOWING_PROMPT = """
=== AGENT INSTRUCTIONS (system prompt) ===
{instructions}

=== USER QUESTION ===
{question}

=== TOOL CALL TRAJECTORY (tool name + arguments only; results omitted) ===
{tools}

=== AGENT ANSWER ===
{agent_answer}
""".strip()


def format_instruction_prompt(entry: dict[str, Any]) -> str:
    return INSTRUCTION_FOLLOWING_PROMPT.format(
        instructions=AGENT_INSTRUCTIONS,
        question=entry["input"]["question"],
        tools=_format_tools(entry.get("tools", [])),
        agent_answer=entry["rag_response"]["answer"],
    )


# ── Check 3: Trajectory optimality ───────────────────────────────────────────
TRAJECTORY_INSTRUCTIONS = """
You are an expert evaluator. You will be given:
1. A user question.
2. The sequence of tool calls (the "trajectory") the agent made.

The agent has ONE tool:
- search(query) — searches the course FAQ and returns matching entries.

The agent is expected to ground its answer in the FAQ, so it should call
`search` at least once. It may search a few times with different queries to
explore a multi-part question. A NORMAL trajectory is 1-3 relevant searches.

You are evaluating ONLY the tool-call trajectory — whether the agent searched
enough, and not wastefully. You are NOT evaluating the answer's correctness
(that is a separate check), and you are NOT shown the search results.

Mark "good" if the trajectory was reasonable:
- 1-3 searches whose queries are relevant to the question, with no exact
  duplicate queries.

Mark "bad" only for CLEAR, OBJECTIVE problems:
- ZERO searches (the agent answered without consulting the FAQ at all).
- The exact same query issued more than once (duplicate/looping).
- Excessive searching (more than 4 search calls).
- Search queries clearly unrelated to the user's question.

Do NOT mark bad just because you think fewer searches could have sufficed.
Provide a concrete suggestion for improvement, or "none" if it was reasonable.
""".strip()

TRAJECTORY_PROMPT = """
User Question:
{question}

Tool Call Trajectory (tool name + arguments only; results omitted):
{tools}
""".strip()


def _format_tools(tools: list[dict]) -> str:
    parts = []
    for i, t in enumerate(tools, 1):
        args = t.get("args", {})
        args_str = json.dumps(args, separators=(",", ":")) if isinstance(args, dict) else str(args)
        parts.append(f"{i}. {t['name']}({args_str})")
    return "\n".join(parts) or "(no tool calls)"


def format_trajectory_prompt(entry: dict[str, Any]) -> str:
    return TRAJECTORY_PROMPT.format(
        question=entry["input"]["question"],
        tools=_format_tools(entry.get("tools", [])),
    )


# ── Check registry ───────────────────────────────────────────────────────────
def _text_format(model: type[BaseModel]) -> dict:
    """Responses `text.format` param with a strict JSON schema for `model`."""
    return {
        "type": "json_schema",
        "name": model.__name__,
        "schema": to_strict_json_schema(model),
        "strict": True,
    }


CHECKS = [
    {
        "name": "correctness",
        "result_key": "judge_answer_correctness",
        "model": CorrectnessResult,
        "instructions": CORRECTNESS_INSTRUCTIONS,
        "format": format_correctness_prompt,
        "text_format": _text_format(CorrectnessResult),
    },
    {
        "name": "instruction",
        "result_key": "judge_instruction_following",
        "model": InstructionFollowingResult,
        "instructions": INSTRUCTION_FOLLOWING_INSTRUCTIONS,
        "format": format_instruction_prompt,
        "text_format": _text_format(InstructionFollowingResult),
    },
    {
        "name": "trajectory",
        "result_key": "judge_trajectory",
        "model": TrajectoryResult,
        "instructions": TRAJECTORY_INSTRUCTIONS,
        "format": format_trajectory_prompt,
        "text_format": _text_format(TrajectoryResult),
    },
]
