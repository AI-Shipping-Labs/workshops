from typing import Any

import dotenv
import logfire
from telegram import Chat, Message, Update, User
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from investment_coach_bot.agent import (
    AgentCouldNotAnswer,
    InvestmentAgentConfig,
    create_agent,
    run_agent,
)
from investment_coach_bot.config import Settings, get_settings
from investment_coach_bot.sec import SecClient
from investment_coach_bot.tools import InvestmentResearchTools


START_MESSAGE = (
    "Investment Coach is ready. Ask for public-company research, for example:\n\n"
    "Analyze NVDA fundamentals\n"
    "Should I buy Tesla now?\n\n"
    "Educational research only: no personalized financial advice, price forecasts, "
    "or buy/sell/hold recommendations."
)
MAX_TELEGRAM_MESSAGE_LENGTH = 4096


class TelegramInvestmentBot:
    def __init__(self, settings: Settings):
        sec = SecClient(settings.sec_user_agent, settings.http_timeout_seconds)
        tools = InvestmentResearchTools(sec)

        self.agent = create_agent(
            InvestmentAgentConfig(model=settings.openai_model),
            tools,
        )
        self.message_history_by_chat: dict[int, list[Any]] = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_command(update, "start", START_MESSAGE)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_command(update, "help", START_MESSAGE)

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        message = update.effective_message
        user = update.effective_user
        if chat is None or message is None:
            return

        metadata = telegram_metadata(chat, user, message)
        with logfire.span("telegram.command", command="stop", **metadata):
            self.message_history_by_chat.pop(chat.id, None)

            chunk_count = await self._reply(message, "Conversation reset.")
            logfire.info(
                "telegram.command.completed",
                command="stop",
                response_chunk_count=chunk_count,
                **metadata,
            )

    async def reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        message = update.effective_message
        user = update.effective_user
        if chat is None or message is None or message.text is None:
            return

        user_prompt = message.text.strip()
        if not user_prompt:
            return

        message_history = self.message_history_by_chat.setdefault(chat.id, [])
        history_length_before = len(message_history)
        metadata = telegram_metadata(chat, user, message)

        with logfire.span(
            "telegram.message",
            prompt=user_prompt,
            prompt_length=len(user_prompt),
            history_length_before=history_length_before,
            **metadata,
        ):
            await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)

            try:
                result = await run_agent(self.agent, user_prompt, message_history)
                new_messages = result.new_messages()
                message_history.extend(new_messages)
                response = result.output.answer
                logfire.info(
                    "telegram.agent.completed",
                    response=response,
                    response_length=len(response),
                    new_message_count=len(new_messages),
                    history_length_after=len(message_history),
                    **metadata,
                )
            except AgentCouldNotAnswer as exc:
                response = str(exc)
                logfire.info(
                    "telegram.agent.could_not_answer",
                    response=response,
                    history_length_after=len(message_history),
                    **metadata,
                )
            except Exception as exc:
                logfire.exception(
                    "telegram.agent.error",
                    error=str(exc),
                    **metadata,
                )
                response = f"I hit an agent error while preparing the response: {exc}"

            chunk_count = await self._reply(message, response)
            logfire.info(
                "telegram.message.replied",
                response_chunk_count=chunk_count,
                **metadata,
            )

    def build_application(self, token: str) -> Application:
        application = ApplicationBuilder().token(token).build()
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("stop", self.stop))
        application.add_handler(CommandHandler("reset", self.stop))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.reply)
        )
        return application

    def run_polling(self, token: str) -> None:
        application = self.build_application(token)
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def _handle_command(self, update: Update, command: str, response: str) -> None:
        chat = update.effective_chat
        message = update.effective_message
        user = update.effective_user
        if chat is None or message is None:
            return

        metadata = telegram_metadata(chat, user, message)
        with logfire.span("telegram.command", command=command, **metadata):
            chunk_count = await self._reply(message, response)
            logfire.info(
                "telegram.command.completed",
                command=command,
                response_chunk_count=chunk_count,
                **metadata,
            )

    async def _reply(self, message: Message, text: str) -> int:
        chunks = split_telegram_message(text)
        for chunk in chunks:
            await message.reply_text(chunk)

        return len(chunks)


def main() -> None:
    configure_monitoring()
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Add it to .env first.")

    bot = TelegramInvestmentBot(settings)
    bot.run_polling(settings.telegram_bot_token)


def configure_monitoring() -> None:
    dotenv.load_dotenv()
    logfire.configure()
    logfire.instrument_pydantic_ai()


def split_telegram_message(text: str) -> list[str]:
    if len(text) <= MAX_TELEGRAM_MESSAGE_LENGTH:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > MAX_TELEGRAM_MESSAGE_LENGTH:
        split_at = remaining.rfind("\n", 0, MAX_TELEGRAM_MESSAGE_LENGTH + 1)
        if split_at <= 0:
            split_at = MAX_TELEGRAM_MESSAGE_LENGTH

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def telegram_metadata(
    chat: Chat,
    user: User | None,
    message: Message,
) -> dict[str, Any]:
    return {
        "chat_id": chat.id,
        "chat_type": chat.type,
        "user_id": user.id if user is not None else None,
        "username": user.username if user is not None else None,
        "message_id": message.message_id,
    }


if __name__ == "__main__":
    main()
