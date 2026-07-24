from aiogram.fsm.state import State, StatesGroup


class CreateProject(StatesGroup):
    name = State()


class AddFile(StatesGroup):
    waiting = State()      # data: project_id


class NewCalc(StatesGroup):
    comment = State()      # data: project_id
