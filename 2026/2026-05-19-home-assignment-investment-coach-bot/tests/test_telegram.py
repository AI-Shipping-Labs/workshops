from contextlib import nullcontext
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from investment_coach_bot.config import Settings
from investment_coach_bot.telegram import (
    MAX_TELEGRAM_MESSAGE_LENGTH,
    TelegramInvestmentBot,
    split_telegram_message,
)


@dataclass
class FakeAgentOutput:
    answer: str


@dataclass
class FakeAgentResult:
    output: FakeAgentOutput
    messages: list[str] = field(default_factory=list)

    def new_messages(self) -> list[str]:
        return self.messages


class FakeMessage:
    def __init__(self, text: str, message_id: int = 1):
        self.text = text
        self.message_id = message_id
        self.replies = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeBot:
    def __init__(self):
        self.chat_actions = []

    async def send_chat_action(self, chat_id: int, action: str) -> None:
        self.chat_actions.append((chat_id, action))


def create_update(chat_id: int, text: str):
    message = FakeMessage(text)
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id, type="private"),
        effective_user=SimpleNamespace(id=789, username="test_user"),
        effective_message=message,
    )
    return update, message


def create_bot() -> TelegramInvestmentBot:
    settings = Settings(
        OPENAI_MODEL="openai:gpt-5.4-mini",
        SEC_USER_AGENT="investment-coach-bot/0.1 tests@example.com",
    )
    return TelegramInvestmentBot(settings)


@pytest.fixture(autouse=True)
def mute_logfire(monkeypatch) -> None:
    monkeypatch.setattr(
        "investment_coach_bot.telegram.logfire.span",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setattr(
        "investment_coach_bot.telegram.logfire.info",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "investment_coach_bot.telegram.logfire.exception",
        lambda *args, **kwargs: None,
    )


@pytest.mark.asyncio
async def test_telegram_reply_runs_agent_and_replies(monkeypatch) -> None:
    bot = create_bot()
    update, message = create_update(123, "Analyze NVDA fundamentals")
    context = SimpleNamespace(bot=FakeBot())
    calls = []

    async def fake_run_agent(agent, user_prompt, message_history, show_trace=False):
        calls.append((user_prompt, list(message_history)))
        return FakeAgentResult(FakeAgentOutput("Research response"), ["new-message"])

    monkeypatch.setattr("investment_coach_bot.telegram.run_agent", fake_run_agent)

    await bot.reply(update, context)

    assert calls == [("Analyze NVDA fundamentals", [])]
    assert bot.message_history_by_chat[123] == ["new-message"]
    assert message.replies == ["Research response"]
    assert context.bot.chat_actions


@pytest.mark.asyncio
async def test_telegram_keeps_message_history_per_chat(monkeypatch) -> None:
    bot = create_bot()
    first_update, _ = create_update(123, "Analyze NVDA")
    second_update, _ = create_update(456, "Analyze MSFT")
    context = SimpleNamespace(bot=FakeBot())
    seen_histories = []

    async def fake_run_agent(agent, user_prompt, message_history, show_trace=False):
        seen_histories.append(list(message_history))
        return FakeAgentResult(FakeAgentOutput("Research response"), [user_prompt])

    monkeypatch.setattr("investment_coach_bot.telegram.run_agent", fake_run_agent)

    await bot.reply(first_update, context)
    await bot.reply(second_update, context)

    assert seen_histories == [[], []]
    assert bot.message_history_by_chat[123] == ["Analyze NVDA"]
    assert bot.message_history_by_chat[456] == ["Analyze MSFT"]


@pytest.mark.asyncio
async def test_telegram_stop_resets_chat_history() -> None:
    bot = create_bot()
    update, message = create_update(123, "/stop")
    context = SimpleNamespace(bot=FakeBot())
    bot.message_history_by_chat[123] = ["old-message"]

    await bot.stop(update, context)

    assert 123 not in bot.message_history_by_chat
    assert message.replies == ["Conversation reset."]


def test_split_telegram_message_keeps_chunks_under_limit() -> None:
    text = ("A" * MAX_TELEGRAM_MESSAGE_LENGTH) + "\nSecond message"

    chunks = split_telegram_message(text)

    assert chunks == ["A" * MAX_TELEGRAM_MESSAGE_LENGTH, "Second message"]
    assert all(len(chunk) <= MAX_TELEGRAM_MESSAGE_LENGTH for chunk in chunks)
