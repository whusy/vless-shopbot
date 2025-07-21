import logging
import os
from urllib.parse import urlparse

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..data_manager.database import update_setting
from . import keyboards

ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")
logger = logging.getLogger(__name__)
admin_router = Router()

class AdminEdit(StatesGroup):
    waiting_for_about_text = State()
    waiting_for_terms_url = State()
    waiting_for_privacy_url = State()
    waiting_for_support_user = State()
    waiting_for_support_text = State()

def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

@admin_router.message(Command("admin"))
async def admin_panel_handler(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("Добро пожаловать в админ-панель!", reply_markup=keyboards.create_admin_keyboard())

@admin_router.callback_query(F.data.startswith("admin_edit_"))
async def start_editing_handler(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[2]
    prompts = {
        "about": ("Пришлите новый текст для раздела 'О проекте'.", AdminEdit.waiting_for_about_text),
        "terms": ("Пришлите новую ссылку на Условия использования.", AdminEdit.waiting_for_terms_url),
        "privacy": ("Пришлите новую ссылку на Политику конфиденциальности.", AdminEdit.waiting_for_privacy_url),
        "support_user": ("Пришлите новую ссылку на поддержку.", AdminEdit.waiting_for_support_user),
        "support_text": ("Пришлите новый текст для раздела 'Поддержка'.", AdminEdit.waiting_for_support_text),
    }
    if action in prompts:
        prompt_text, new_state = prompts[action]
        await callback.message.edit_text(prompt_text, reply_markup=keyboards.create_admin_cancel_keyboard())
        await state.set_state(new_state)
    await callback.answer()

@admin_router.callback_query(F.data == "admin_cancel_edit")
async def cancel_editing_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Действие отменено. Вы в админ-панели.", reply_markup=keyboards.create_admin_keyboard())
    await callback.answer()

async def process_new_content(message: types.Message, state: FSMContext, db_key: str):
    update_setting(db_key, message.text)
    await state.clear()
    await message.answer("✅ Успешно обновлено!", reply_markup=keyboards.create_admin_keyboard())

@admin_router.message(AdminEdit.waiting_for_about_text)
async def process_about_text(message: types.Message, state: FSMContext):
    await process_new_content(message, state, "about_text")


@admin_router.message(AdminEdit.waiting_for_terms_url)
async def process_terms_url(message: types.Message, state: FSMContext):
    if is_valid_url(message.text):
        await process_new_content(message, state, "terms_url")
    else:
        await message.answer("❌ **Ошибка:** Это не похоже на валидную ссылку. Она должна начинаться с `http://` или `https://`. Попробуйте еще раз или нажмите 'Отмена'.")

@admin_router.message(AdminEdit.waiting_for_privacy_url)
async def process_privacy_url(message: types.Message, state: FSMContext):
    if is_valid_url(message.text):
        await process_new_content(message, state, "privacy_url")
    else:
        await message.answer("❌ **Ошибка:** Это не похоже на валидную ссылку. Она должна начинаться с `http://` или `https://`. Попробуйте еще раз или нажмите 'Отмена'.")

@admin_router.message(AdminEdit.waiting_for_support_user)
async def process_support_user(message: types.Message, state: FSMContext):
    if is_valid_url(message.text):
        await process_new_content(message, state, "support_user")
    else:
        await message.answer("❌ **Ошибка:** Это не похоже на валидную ссылку. Она должна начинаться с `http://` или `https://`. Попробуйте еще раз или нажмите 'Отмена'.")

@admin_router.message(AdminEdit.waiting_for_support_text)
async def process_support_text(message: types.Message, state: FSMContext):
    await process_new_content(message, state, "support_text")