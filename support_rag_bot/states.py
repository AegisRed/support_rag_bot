from aiogram.fsm.state import State, StatesGroup


class TicketStates(StatesGroup):
    waiting_for_ticket = State()
    clarifying_ticket = State()
    operator_handoff = State()
