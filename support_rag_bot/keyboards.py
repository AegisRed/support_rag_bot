from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Новый тикет", callback_data="ticket:new")],
            [
                InlineKeyboardButton(text="Примеры", callback_data="ticket:examples"),
                InlineKeyboardButton(text="База знаний", callback_data="ticket:kb"),
            ],
        ]
    )
