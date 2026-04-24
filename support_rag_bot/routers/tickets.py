from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from support_rag_bot.config import Settings
from support_rag_bot.keyboards import main_menu_keyboard
from support_rag_bot.services.rag_service import RAGService, format_ticket_result
from support_rag_bot.states import TicketStates

router = Router(name="tickets")


@router.message(Command("newticket"))
async def new_ticket_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(TicketStates.waiting_for_ticket)
    await state.update_data(history=[], clarification_round=0, shown_doc_ids=[])
    await message.answer(
        "Опиши проблему одним сообщением. Можно свободно: что случилось, где ломается и что уже пробовали.",
    )


@router.callback_query(F.data == "ticket:new")
async def new_ticket_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TicketStates.waiting_for_ticket)
    await state.update_data(history=[], clarification_round=0, shown_doc_ids=[])
    await callback.message.edit_text(
        "Опиши проблему одним сообщением. Можно свободно: что случилось, где ломается и что уже пробовали.",
    )
    await callback.answer()


@router.callback_query(F.data == "ticket:kb")
@router.message(Command("kb"))
async def kb_handler(event: CallbackQuery | Message, rag_service: RAGService) -> None:
    docs = await rag_service.list_documents()
    text = "<b>База знаний</b>\n\n" + "\n".join(
        f'• <a href="{doc.url}">{doc.title}</a> — {doc.section}' for doc in docs[:10]
    )
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=main_menu_keyboard())
        await event.answer()
        return
    await event.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("examples"))
async def examples_handler(message: Message) -> None:
    text = (
        "<b>Примеры тикетов</b>\n\n"
        "1. Я не вижу кнопку экспорта CSV на тарифе Starter.\n"
        "2. Потерял 2FA и у меня нет recovery codes.\n"
        "3. API отвечает 429, что это значит и что делать дальше?\n"
        "4. Где скачать инвойс за прошлый месяц?\n"
        "5. Верните деньги за частично использованный месяц."
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("reindex"))
async def reindex_handler(message: Message, rag_service: RAGService, settings: Settings) -> None:
    if settings.admin_ids and message.from_user.id not in settings.admin_ids:
        await message.answer("Эта команда доступна только администратору бота.")
        return
    await message.answer("Пересобираю seed-базу и эмбеддинги.")
    count = await rag_service.reindex_seed_documents()
    await message.answer(f"Готово. Переиндексировано документов: {count}.", reply_markup=main_menu_keyboard())


@router.message(Command("exitticket"))
@router.message(Command("cancel"))
async def exit_ticket_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Тикет завершён. Возвращаю в меню.", reply_markup=main_menu_keyboard())


@router.message(TicketStates.waiting_for_ticket)
@router.message(TicketStates.clarifying_ticket)
async def ticket_state_input(
    message: Message,
    state: FSMContext,
    rag_service: RAGService,
    settings: Settings,
) -> None:
    await _process_ticket(message, state, rag_service, settings)


@router.message(TicketStates.operator_handoff)
async def operator_mode_message(message: Message) -> None:
    await message.answer(
        "Этот тикет уже переведён в режим ожидания оператора. Я больше не буду пытаться угадывать ответ по базе знаний. "
        "Если есть важные детали, можешь прислать их сюда. Завершить тикет — /exitticket."
    )


@router.message(F.text)
async def plain_text_ticket(
    message: Message,
    state: FSMContext,
    rag_service: RAGService,
    settings: Settings,
) -> None:
    if message.text and message.text.startswith("/"):
        return
    await state.set_state(TicketStates.waiting_for_ticket)
    await state.update_data(history=[], clarification_round=0, shown_doc_ids=[])
    await _process_ticket(message, state, rag_service, settings)


async def _process_ticket(
    message: Message,
    state: FSMContext,
    rag_service: RAGService,
    settings: Settings,
) -> None:
    ticket_text = (message.text or "").strip()
    if not ticket_text:
        await message.answer("Нужен текст тикета.")
        return

    data = await state.get_data()
    history = list(data.get("history", []))
    shown_doc_ids = set(data.get("shown_doc_ids", []))
    clarification_round = int(data.get("clarification_round", 0))
    history.append(ticket_text)

    progress = await message.answer("Подождите...")
    result = await rag_service.answer_ticket(history, clarification_round=clarification_round)
    await rag_service.store.log_ticket(
        user_id=message.from_user.id,
        username=message.from_user.username,
        result=result,
    )
    formatted_text, newly_shown_ids = format_ticket_result(
        result,
        settings=settings,
        shown_doc_ids=shown_doc_ids,
    )
    shown_doc_ids.update(newly_shown_ids)
    await progress.edit_text(formatted_text)

    if result.mode == "clarify":
        await state.set_state(TicketStates.clarifying_ticket)
        await state.update_data(
            history=history,
            clarification_round=clarification_round + 1,
            shown_doc_ids=list(shown_doc_ids),
        )
        return

    if result.mode == "handoff":
        await state.set_state(TicketStates.operator_handoff)
        await state.update_data(
            history=history,
            clarification_round=clarification_round,
            shown_doc_ids=list(shown_doc_ids),
        )
        return

    await state.clear()
