from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from support_rag_bot.config import get_settings
from support_rag_bot.logging_setup import configure_logging
from support_rag_bot.routers.start import router as start_router
from support_rag_bot.routers.tickets import router as tickets_router
from support_rag_bot.services.gemini_service import GeminiService
from support_rag_bot.services.rag_service import RAGService
from support_rag_bot.services.storage import KnowledgeBaseStore

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the Telegram bot.")

    bot = Bot(token=settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    store = KnowledgeBaseStore(settings.db_path)
    gemini = GeminiService(
        api_key=settings.gemini_api_key,
        generation_model=settings.gemini_generation_model,
        embedding_model=settings.gemini_embedding_model,
    )
    rag_service = RAGService(
        store=store,
        gemini=gemini,
        settings=settings,
    )
    await rag_service.bootstrap()

    dp["rag_service"] = rag_service
    dp["settings"] = settings

    dp.include_router(start_router)
    dp.include_router(tickets_router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть стартовый экран"),
            BotCommand(command="newticket", description="Ввести новый тикет"),
            BotCommand(command="exitticket", description="Завершить текущий тикет"),
            BotCommand(command="kb", description="Посмотреть базу знаний"),
            BotCommand(command="examples", description="Показать примеры тикетов"),
        ]
    )
    await bot.set_my_description(
        "RAG-ассистент для саппорта: отвечает по базе знаний, умеет уточнять детали и честно передавать кейс оператору."
    )
    await bot.set_my_short_description("RAG-ассистент для саппорта")

    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
