# Test Guidelines

These guidelines describe the testing style expected in this project.

The main principle is simple: test observable behavior, not implementation wording.

For an agent, observable behavior means:

- what answer the user receives;
- which tools the agent called;
- whether the answer follows product rules;
- whether data parsing code returns correct values.

It does not mean checking that a prompt contains a specific sentence.

## Test Categories

Use two kinds of tests.

### Deterministic Tests

These are normal pytest tests. They should have clear pass/fail assertions.

Use them for:

- SEC data parsing;
- company lookup;
- tool-call behavior;
- forbidden terminology checks;
- output safety checks;
- answer shape checks that can be expressed exactly.

### Judge Tests

Use judge tests later for subjective quality.

Use them for:

- whether the answer is useful;
- whether it is concise enough;
- whether it avoids generic company description;
- whether the analysis is balanced;
- whether the answer explains why metrics matter.

Judge tests should not replace deterministic tests.

## Agent Test Style

Follow the style from the documentation-agent example:

```python
@pytest.mark.asyncio
async def test_agent_includes_code_in_answer(agent):
    user_prompt = "llm as a judge"
    result = await run_agent_test(agent, user_prompt)

    answer = result.output
    assert "```python" in answer.answer
```

For this project, write tests in the same shape:

```python
@pytest.mark.asyncio
async def test_agent_avoids_forbidden_terminology() -> None:
    agent = create_test_agent()

    user_prompt = "what can you tell me about reddit"

    result = await agent.run(user_prompt)
    answer = result.output

    forbidden_terms = [
        "bull case",
        "base case",
        "bear case",
    ]

    assert len(find_terms(answer.answer, forbidden_terms)) == 0
```

The structure should be easy to scan:

1. create the agent;
2. define the user prompt;
3. run the agent;
4. extract the output or tool calls;
5. assert the behavior.

Keep blank lines between these blocks.

## Real Model Agent Tests

For agent behavior tests, call the configured OpenAI model.

Do not use `TestModel` with canned output for tests that are supposed to check behavior. Canned output proves only that the test fixture returned what we hardcoded.

Bad:

```python
model = TestModel(
    custom_output_args={
        "answer": "Verdict\n- SEC data was used.",
    }
)
```

This does not prove the agent can produce a good answer.

Prefer:

```python
settings = get_settings()
tools = InvestmentResearchTools(FakeSecClient())
agent = create_agent(InvestmentAgentConfig(model=settings.openai_model), tools)

result = await agent.run("what can you tell me about reddit")
```

If `OPENAI_API_KEY` is missing, let the test fail naturally. Do not silently skip required agent tests.

## Tool-Call Tests

Tool-call tests should inspect `result.new_messages()` and collect tool calls.

Good:

```python
tool_calls = collect_tools(result.new_messages())
tool_names = [tool.name for tool in tool_calls]

assert "search_company" in tool_names
assert "get_financial_snapshot" in tool_names
assert "get_filing_digest" in tool_names
```

Do not assert exact tool order unless the order is part of the required behavior.

## Output Rule Tests

Some answer-quality rules can be deterministic.

Examples:

- forbidden terminology is absent;
- the answer is not empty;
- required sections are present;
- raw JSON is not included;
- buy/sell/hold advice is not included.

These tests should check the final answer, not the prompt.

Bad:

```python
assert "bull case" not in DEFAULT_INSTRUCTIONS
```

Good:

```python
answer = result.output

forbidden_terms = [
    "bull case",
    "base case",
    "bear case",
]

assert len(find_terms(answer.answer, forbidden_terms)) == 0
```

The user sees `answer.answer`, not `DEFAULT_INSTRUCTIONS`.

## Helper Style

Use helpers only when they remove real duplication.

Good shared helpers:

- `FakeSecClient`, because multiple agent tests may need stable SEC data;
- `collect_tools`, because tool-call extraction is noisy.

Keep test-specific data inside the test when it improves readability.

For example, keep `forbidden_terms` inside `test_agent_avoids_forbidden_terminology` unless several tests reuse the exact same list.

Do not create helpers that hide the point of the test.

Bad:

```python
def build_test_agent(model):
    ...
```

if it is used once and makes the setup less explicit.

## Coding Style In Tests

Prefer clear, boring Python.

- Use explicit `for` loops over dense list comprehensions when readability matters.
- Prefer direct assertions over clever helpers.
- Keep arrange/run/assert blocks visually separated.
- Avoid inline imports.
- Avoid testing private methods when a public method can expose the behavior.
- Avoid testing exact prompt wording.
- Avoid vague test names.

Good helper:

```python
def find_terms(text: str, terms: list[str]) -> list[str]:
    found_terms = []

    for term in terms:
        pattern = rf"\b{re.escape(term)}\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            found_terms.append(term)

    return found_terms
```

## SEC Tests

SEC parsing tests are useful because they protect real data behavior.

Good SEC tests:

- search by company name returns the expected ticker and normalized CIK;
- annual facts ignore quarterly rows;
- annual facts deduplicate overlapping period ends;
- Reddit revenue uses `RevenueFromContractWithCustomerExcludingAssessedTax`;
- filing snippets are extracted from realistic filing-like text.

Weak SEC tests:

- tests that use toy text unrelated to real filings;
- tests that check only topic names but not snippet quality;
- tests that use awkward fake objects instead of the real dataclass;
- tests that call private helpers when a public method can be used.

Private helper tests are acceptable only when the parsing logic is important and difficult to reach cleanly through public methods.

## What Not To Test

Do not write tests that only prove:

- the agent object can be constructed;
- a prompt contains a phrase;
- a Pydantic field description contains a phrase;
- a canned model response contains a hardcoded word;
- tool names appear in the tool list without running the agent.

These tests are cheap to write but do not protect the product.

## Current Direction

The preferred agent tests are:

- real OpenAI-backed async tests;
- fake SEC client for stable data;
- observable assertions on final answer and tool calls;
- simple helper functions only for repeated mechanics;
- no prompt-string assertions;
- no canned model answers.
