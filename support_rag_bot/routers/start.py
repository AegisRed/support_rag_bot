from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from support_rag_bot.keyboards import main_menu_keyboard

router = Router(name="start")


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = (
        "<b>Support RAG Assistant</b>\n\n"
        "Отправь проблему обычным сообщением или нажми кнопку ниже.\n\n"
        "Бот сначала ищет ответ в базе знаний. Если по материалам можно ответить уверенно — отвечает. "
        "Если нет, он может коротко уточнить детали. Когда по базе знаний лучше не гадать, тикет переводится на ручной разбор."
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    text = (
        "<b>Команды</b>\n"
        "/start — стартовый экран\n"
        "/help — короткая справка\n"
        "/newticket — начать новый тикет\n"
        "/exitticket — завершить текущий тикет и вернуться в меню\n"
        "/kb — показать документы базы знаний\n"
        "/examples — примеры тикетов\n"
        "/reindex — пересобрать эмбеддинги seed-базы"
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "ticket:examples")
async def examples_callback(callback: CallbackQuery) -> None:
    text = (
        "<b>Примеры тикетов</b>\n\n"
        "1. Я не вижу кнопку экспорта CSV на тарифе Starter.\n"
        "2. Потерял 2FA и у меня нет recovery codes.\n"
        "3. API отвечает 429, что это значит и что делать дальше?\n"
        "4. Где скачать инвойс за прошлый месяц?\n"
        "5. Верните деньги за частично использованный месяц."
    )
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard())
    await callback.answer()
