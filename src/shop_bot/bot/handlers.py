import logging
import uuid
from io import BytesIO
from datetime import datetime, timedelta
import qrcode
from yookassa import Payment
import aiohttp
import os
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
import requests

from aiogram import Bot, Router, F, types, html
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType

from shop_bot.bot import keyboards
from shop_bot.modules import xui_api
from shop_bot.data_manager.database import (
    get_user, add_new_key, get_user_keys, update_user_stats,
    register_user_if_not_exists, get_next_key_number, get_key_by_id,
    update_key_info, set_trial_used, set_terms_agreed, get_setting
)
from shop_bot.config import (
    PLANS, CHOOSE_PLAN_MESSAGE, WELCOME_MESSAGE, 
    get_profile_text, get_vpn_active_text, VPN_INACTIVE_TEXT, VPN_NO_DATA_TEXT,
    get_key_info_text, CHOOSE_PAYMENT_METHOD_MESSAGE, get_purchase_success_text, ABOUT_TEXT, TERMS_URL, PRIVACY_URL, SUPPORT_USER, SUPPORT_TEXT, CHANNEL_URL
)

TELEGRAM_BOT_USERNAME = None
CRYPTO_API_KEY = None
CRYPTO_MERCHANT_ID = None
PAYMENT_METHODS = None
PLANS = None
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")
MAIN_REMARK = os.getenv("MAIN_REMARK")

logger = logging.getLogger(__name__)
admin_router = Router()
user_router = Router()

async def show_main_menu(message: types.Message, edit_message: bool = False):
    user_id = message.chat.id
    user_db_data = get_user(user_id)
    user_keys = get_user_keys(user_id)
    
    trial_available = not (user_db_data and user_db_data.get('trial_used'))
    is_admin = str(user_id) == ADMIN_ID

    text = "🏠 <b>Главное меню</b>\n\nВыберите действие:"
    keyboard = keyboards.create_main_menu_keyboard(user_keys, trial_available, is_admin)
    
    if edit_message:
        try:
            await message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest:
            pass
    else:
        await message.answer(text, reply_markup=keyboard)

class UserAgreement(StatesGroup):
    waiting_for_agreement = State()

@user_router.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.full_name
    
    register_user_if_not_exists(user_id, username)
    user_data = get_user(user_id)

    if user_data and user_data.get('agreed_to_terms'):
        await message.answer(
            f"👋 Снова здравствуйте, {html.bold(message.from_user.full_name)}!",
            reply_markup=keyboards.main_reply_keyboard
        )
        await show_main_menu(message)
    else:
        terms_url = get_setting("terms_url")
        privacy_url = get_setting("privacy_url")
        if not terms_url or not privacy_url:
            await message.answer("❗️ Условия использования и политика конфиденциальности не установлены. Пожалуйста, обратитесь к администратору.")
            return
        agreement_text = (
            "<b>Добро пожаловать!</b>\n\n"
            "Перед началом использования бота, пожалуйста, ознакомьтесь и примите наши "
            f"<a href='{terms_url}'>Условия использования</a> и "
            f"<a href='{privacy_url}'>Политику конфиденциальности</a>.\n\n"
            "Нажимая кнопку 'Принимаю', вы подтверждаете свое согласие с этими документами."
        )
        await message.answer(agreement_text, reply_markup=keyboards.create_agreement_keyboard(), disable_web_page_preview=True)
        await state.set_state(UserAgreement.waiting_for_agreement)

@user_router.callback_query(UserAgreement.waiting_for_agreement, F.data == "agree_to_terms")
async def agree_to_terms_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    
    set_terms_agreed(user_id)
    
    await state.clear()
    
    await callback.message.delete()
    
    await callback.message.answer(
        f"✅ Спасибо! Приятного использования.",
        reply_markup=keyboards.main_reply_keyboard
    )
    await show_main_menu(callback.message)

@user_router.message(UserAgreement.waiting_for_agreement)
async def agreement_fallback_handler(message: types.Message):
    await message.answer("Пожалуйста, сначала примите условия использования, нажав на кнопку выше.")

@user_router.message(F.text == "🏠 Главное меню")
async def main_menu_handler(message: types.Message):
    await show_main_menu(message)

@user_router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu_handler(callback: types.CallbackQuery):
    await callback.answer()
    await show_main_menu(callback.message, edit_message=True)

@user_router.callback_query(F.data == "show_profile")
async def profile_handler_callback(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    user_db_data = get_user(user_id)
    user_keys = get_user_keys(user_id)
    if not user_db_data:
        await callback.answer("Не удалось получить данные профиля.", show_alert=True)
        return
    username = html.bold(user_db_data.get('username', 'Пользователь'))
    total_spent, total_months = user_db_data.get('total_spent', 0), user_db_data.get('total_months', 0)
    now = datetime.now()
    active_keys = [key for key in user_keys if datetime.fromisoformat(key['expiry_date']) > now]
    if active_keys:
        latest_key = max(active_keys, key=lambda k: datetime.fromisoformat(k['expiry_date']))
        latest_expiry_date = datetime.fromisoformat(latest_key['expiry_date'])
        time_left = latest_expiry_date - now
        vpn_status_text = get_vpn_active_text(time_left.days, time_left.seconds // 3600)
    elif user_keys: vpn_status_text = VPN_INACTIVE_TEXT
    else: vpn_status_text = VPN_NO_DATA_TEXT
    final_text = get_profile_text(username, total_spent, total_months, vpn_status_text)
    await callback.message.edit_text(final_text, reply_markup=keyboards.create_back_to_menu_keyboard())

@user_router.callback_query(F.data == "show_about")
async def about_handler(callback: types.CallbackQuery):
    await callback.answer()
    
    about_text = get_setting("about_text")
    terms_url = get_setting("terms_url")
    privacy_url = get_setting("privacy_url")

    if about_text == ABOUT_TEXT and terms_url == TERMS_URL and privacy_url == PRIVACY_URL:
        await callback.message.edit_text(
            "Информация о проекте не установлена. Установите её в админ-панели.",
            reply_markup=keyboards.create_back_to_menu_keyboard()
        )
    elif terms_url == TERMS_URL and privacy_url == PRIVACY_URL:
        await callback.message.edit_text(
            about_text,
            reply_markup=keyboards.create_back_to_menu_keyboard()
        )
    elif terms_url == TERMS_URL:
        await callback.message.edit_text(
            about_text,
            reply_markup=keyboards.create_about_keyboard_terms(privacy_url)
        )
    elif privacy_url == PRIVACY_URL:
        await callback.message.edit_text(
            about_text,
            reply_markup=keyboards.create_about_keyboard_privacy(terms_url)
        )
    else:
        await callback.message.edit_text(
        about_text,
        reply_markup=keyboards.create_about_keyboard(terms_url, privacy_url)
        )

@user_router.callback_query(F.data == "show_help")
async def about_handler(callback: types.CallbackQuery):
    await callback.answer()

    support_user = get_setting("support_user")
    support_text = get_setting("support_text")

    if support_user == SUPPORT_USER and support_text == SUPPORT_TEXT:
        await callback.message.edit_text(
            support_user,
            reply_markup=keyboards.create_back_to_menu_keyboard()
        )
    elif support_text == SUPPORT_TEXT:
        await callback.message.edit_text(
            "Для связи с поддержкой используйте кнопку ниже.",
            reply_markup=keyboards.create_support_keyboard(support_user)
        )
    else:
        await callback.message.edit_text(
            support_text + "\n\n" + "Для связи с поддержкой используйте кнопку ниже.",
            reply_markup=keyboards.create_support_keyboard(support_user)
        )

@user_router.callback_query(F.data == "manage_keys")
async def manage_keys_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    user_keys = get_user_keys(user_id)
    await callback.message.edit_text(
        "Ваши ключи:" if user_keys else "У вас пока нет ключей, давайте создадим первый!",
        reply_markup=keyboards.create_keys_management_keyboard(user_keys)
    )

@user_router.callback_query(F.data == "get_trial")
async def trial_period_handler(callback: types.CallbackQuery):
    await callback.answer("Проверяю доступность...", show_alert=False)
    user_id = callback.from_user.id
    user_db_data = get_user(user_id)
    if user_db_data and user_db_data.get('trial_used'):
        await callback.answer("Вы уже использовали бесплатный пробный период.", show_alert=True)
        return
    await callback.message.edit_text("Отлично! Создаю для вас бесплатный ключ на 3 дня...")
    try:
        api, target_inbound = xui_api.login()
        if not api or not target_inbound:
            await callback.message.edit_text("❌ Ошибка на сервере.")
            return
        key_number = get_next_key_number(user_id)
        email = f"user{user_id}-key{key_number}-trial@telegram.bot"
        user_uuid, expiry_timestamp = xui_api.update_or_create_client(api, target_inbound, email, 3)
        if not user_uuid:
            await callback.message.edit_text("❌ Не удалось создать пробный ключ в панели.")
            return
        new_key_id = add_new_key(user_id, user_uuid, email, expiry_timestamp)
        set_trial_used(user_id)
        connection_string = xui_api.get_connection_string(target_inbound, user_uuid, email)
        await callback.message.delete()
        new_expiry_date = datetime.fromtimestamp(expiry_timestamp / 1000)
        final_text = get_purchase_success_text("готов", key_number, new_expiry_date, connection_string)
        await callback.message.answer(text=final_text, reply_markup=keyboards.create_key_info_keyboard(new_key_id))
    except Exception as e:
        logger.error(f"Error creating trial key for user {user_id}: {e}", exc_info=True)
        await callback.message.edit_text("❌ Произошла ошибка при создании пробного ключа.")

@user_router.callback_query(F.data == "open_admin_panel")
async def open_admin_panel_handler(callback: types.CallbackQuery):
    if str(callback.from_user.id) != ADMIN_ID:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return
    
    await callback.answer()
    await callback.message.edit_text(
        "Добро пожаловать в админ-панель!",
        reply_markup=keyboards.create_admin_keyboard()
    )

@user_router.callback_query(F.data.startswith("show_key_"))
async def show_key_handler(callback: types.CallbackQuery):
    key_id_to_show = int(callback.data.split("_")[2])
    await callback.message.edit_text("Загружаю информацию о ключе...")
    user_id = callback.from_user.id
    key_data = get_key_by_id(key_id_to_show)

    if not key_data or key_data['user_id'] != user_id:
        await callback.message.edit_text("❌ Ошибка: ключ не найден.")
        return
        
    try:
        api, target_inbound = xui_api.login()
        if not api or not target_inbound:
            await callback.message.edit_text("❌ Ошибка на сервере.")
            return

        user_uuid = key_data['xui_client_uuid']
        email = key_data['key_email']
        connection_string = xui_api.get_connection_string(target_inbound, user_uuid, email)
        if not connection_string:
            await callback.message.edit_text("❌ Не удалось сгенерировать строку подключения.")
            return
        
        expiry_date = datetime.fromisoformat(key_data['expiry_date'])
        created_date = datetime.fromisoformat(key_data['created_date'])
        
        all_user_keys = get_user_keys(user_id)
        key_number = next((i + 1 for i, key in enumerate(all_user_keys) if key['key_id'] == key_id_to_show), 0)
        
        final_text = get_key_info_text(key_number, expiry_date, created_date, connection_string)
        
        await callback.message.edit_text(
            text=final_text,
            reply_markup=keyboards.create_key_info_keyboard(key_id_to_show)
        )
    except Exception as e:
        logger.error(f"Error showing key {key_id_to_show}: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при получении данных ключа.")

@user_router.callback_query(F.data.startswith("show_qr_"))
async def show_qr_handler(callback: types.CallbackQuery):
    await callback.answer("Генерирую QR-код...")
    key_id = int(callback.data.split("_")[2])
    key_data = get_key_by_id(key_id)
    if not key_data or key_data['user_id'] != callback.from_user.id: return
    
    try:
        api, target_inbound = xui_api.login()
        if not api or not target_inbound: return
        connection_string = xui_api.get_connection_string(target_inbound, key_data['xui_client_uuid'], key_data['key_email'])
        if not connection_string: return

        qr_img = qrcode.make(connection_string)
        bio = BytesIO(); qr_img.save(bio, "PNG"); bio.seek(0)
        qr_code_file = BufferedInputFile(bio.read(), filename="vpn_qr.png")
        await callback.message.answer_photo(photo=qr_code_file)
    except Exception as e:
        logger.error(f"Error showing QR for key {key_id}: {e}")

@user_router.callback_query(F.data.startswith("show_instruction_"))
async def show_instruction_handler(callback: types.CallbackQuery):
    await callback.answer()
    key_id = int(callback.data.split("_")[2])
    instruction_text = (
        "<b>Как подключиться?</b>\n\n"
        "1. Скопируйте ключ подключения (vless://...).\n"
        "2. Скачайте приложение, совместимое с Xray/V2Ray:\n"
        "   - <b>Android:</b> V2RayNG, FoXray\n"
        "   - <b>iOS:</b> FoXray, Streisand, Shadowrocket\n"
        "   - <b>Windows:</b> V2RayN\n"
        "   - <b>macOS:</b> V2RayU, FoXray\n"
        "3. В приложении нажмите 'Импорт из буфера обмена' или '+' и вставьте ключ.\n"
        "4. Запустите VPN-соединение!"
    )
    await callback.message.edit_text(instruction_text, reply_markup=keyboards.create_back_to_key_keyboard(key_id))

@user_router.callback_query(F.data == "buy_new_key")
async def buy_new_key_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("Выберите тариф для нового ключа:", reply_markup=keyboards.create_plans_keyboard(PLANS, action="new"))

@user_router.callback_query(F.data.startswith("extend_key_"))
async def extend_key_handler(callback: types.CallbackQuery):
    key_id = int(callback.data.split("_")[2])
    await callback.answer()
    await callback.message.edit_text("Выберите тариф для продления ключа:", reply_markup=keyboards.create_plans_keyboard(PLANS, action="extend", key_id=key_id))

@user_router.callback_query(F.data.startswith("buy_") & F.data.contains("_month"))
async def choose_payment_method_handler(callback: types.CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    plan_id, action, key_id = "_".join(parts[:-2]), parts[-2], int(parts[-1])
    await callback.message.edit_text(
        CHOOSE_PAYMENT_METHOD_MESSAGE,
        reply_markup=keyboards.create_payment_method_keyboard(PAYMENT_METHODS, plan_id, action, key_id)
    )

@user_router.callback_query(F.data.startswith("pay_yookassa_"))
async def create_yookassa_payment_handler(callback: types.CallbackQuery):
    await callback.answer("Создаю ссылку на оплату...")
    
    parts = callback.data.split("_")[2:]
    plan_id = "_".join(parts[:-2])
    action = parts[-2]
    key_id = int(parts[-1])
    
    if plan_id not in PLANS:
        await callback.message.answer("Произошла ошибка при выборе тарифа.")
        return

    name, price_rub, months = PLANS[plan_id]
    user_id = callback.from_user.id
    chat_id_to_delete = callback.message.chat.id
    message_id_to_delete = callback.message.message_id
    
    try:
        if months == 1:
            description = f"Оплата подписки на 1 месяц"
        elif months <= 5:
            description = f"Оплата подписки на {months} месяца"
        else:
            description = f"Оплата подписки на {months} месяцев"

        payment = Payment.create({
            "amount": {"value": price_rub, "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": f"https://t.me/{TELEGRAM_BOT_USERNAME}"},
            "capture": True, "description": description,
            "metadata": {
                "user_id": user_id, "months": months, "price": price_rub, 
                "action": action, "key_id": key_id,
                "chat_id": chat_id_to_delete, "message_id": message_id_to_delete
            }
        }, uuid.uuid4())
        await callback.message.edit_text(
            "Нажмите на кнопку ниже для оплаты:",
            reply_markup=keyboards.create_payment_keyboard(payment.confirmation.confirmation_url)
        )
    except Exception as e:
        logger.error(f"Failed to create YooKassa payment: {e}", exc_info=True)
        await callback.message.answer("Не удалось создать ссылку на оплату.")

@user_router.callback_query(F.data.startswith("pay_sbp_"))
async def create_sbp_payment_handler(callback: types.CallbackQuery):
    await callback.answer("Создаю ссылку на оплату...")
    
    parts = callback.data.split("_")[2:]
    plan_id = "_".join(parts[:-2])
    action = parts[-2]
    key_id = int(parts[-1])
    
    if plan_id not in PLANS:
        await callback.message.answer("Произошла ошибка при выборе тарифа.")
        return

    name, price_rub, months = PLANS[plan_id]
    user_id = callback.from_user.id
    chat_id_to_delete = callback.message.chat.id
    message_id_to_delete = callback.message.message_id
    
    try:
        if months == 1:
            description = f"Оплата подписки на 1 месяц"
        elif months <= 5:
            description = f"Оплата подписки на {months} месяца"
        else:
            description = f"Оплата подписки на {months} месяцев"

        payment = Payment.create({
            "amount": {"value": price_rub, "currency": "RUB"},
            "payment_method_data": {"type": "sbp"},
            "confirmation": {"type": "redirect", "return_url": f"https://t.me/{TELEGRAM_BOT_USERNAME}"},
            "capture": True, "description": description,
            "metadata": {
                "user_id": user_id, "months": months, "price": price_rub, 
                "action": action, "key_id": key_id,
                "chat_id": chat_id_to_delete, "message_id": message_id_to_delete
            }
        }, uuid.uuid4())
        await callback.message.edit_text(
            "Нажмите на кнопку ниже для оплаты:",
            reply_markup=keyboards.create_payment_keyboard(payment.confirmation.confirmation_url)
        )
    except Exception as e:
        logger.error(f"Failed to create SBP payment: {e}", exc_info=True)
        await callback.message.answer("Не удалось создать ссылку на оплату.")

import hashlib

def create_heleket_signature(payload: dict, api_key: str) -> str:
    """
    Создает сигнатуру для API Heleket на основе рабочего примера.
    Использует жестко заданный, отсортированный список ключей для 100% надежности.
    """
    # 1. Жестко заданный список ключей в алфавитном порядке, как в рабочем примере.
    # Это гарантирует правильный порядок и исключает лишние поля вроде 'metadata'.
    keys_for_sign = [
        'amount', 
        'callback_url', 
        'currency', 
        'description', 
        'fail_url', 
        'merchant_id', 
        'order_id', 
        'success_url'
    ]
    
    # 2. Собираем список значений в правильном порядке.
    # Используем простое преобразование в строку str(), как в примере.
    values = [str(payload[key]) for key in keys_for_sign]
    
    # 3. Соединяем значения через двоеточие.
    sign_string = ":".join(values)
    
    # 4. Добавляем API-ключ и хэшируем.
    string_to_hash = sign_string + api_key

    # Отладка, чтобы убедиться, что все верно
    print(f"DEBUG [Final]: String for hashing: '{string_to_hash}'")
    
    return hashlib.sha256(string_to_hash.encode('utf-8')).hexdigest()

@user_router.callback_query(F.data.startswith("pay_crypto_"))
async def create_crypto_payment_handler(callback: types.CallbackQuery):
    await callback.answer("Создаю счет для оплаты в криптовалюте...")
    
    # Ваша логика парсинга callback.data остается без изменений
    parts = callback.data.split("_")[2:]
    plan_id = "_".join(parts[:-2])
    action = parts[-2]
    key_id = int(parts[-1])

    if plan_id not in PLANS:
        await callback.message.answer("Произошла ошибка при выборе тарифа.")
        return

    name, price_rub, months = PLANS[plan_id]
    user_id = callback.from_user.id
    
    # Получаем URL для вебхуков и имя бота из переменных окружения
    crypto_webhook_url = os.getenv("CRYPTO_WEBHOOK_URL")
    bot_username = os.getenv("TELEGRAM_BOT_USERNAME") # Убедитесь, что эта переменная есть

    try:
        if months == 1:
            description = f"Оплата подписки на 1 месяц"
        elif months <= 4:
            description = f"Оплата подписки на {months} месяца"
        else:
            description = f"Оплата подписки на {months} месяцев"
            
        async with aiohttp.ClientSession() as session:
            # 1. Формируем payload со всеми необходимыми полями
            payload = {
                # ---- Поля, участвующие в подписи ----
                "merchant_id": CRYPTO_MERCHANT_ID,
                "amount": float(price_rub), # Рабочий пример использует float, потом конвертирует в str
                "currency": "RUB",
                "order_id": str(uuid.uuid4()),
                "description": description,
                "callback_url": crypto_webhook_url,
                "success_url": f"https://t.me/{bot_username}",
                "fail_url": f"https://t.me/{bot_username}",
                # ---- Поля, НЕ участвующие в подписи ----
                "metadata": {
                    "user_id": user_id, "months": months, "price": price_rub, 
                    "action": action, "key_id": key_id,
                    "chat_id": callback.message.chat.id, 
                    "message_id": callback.message.message_id
                }
            }

            # 2. Создаем подпись с помощью нашей новой, надежной функции
            signature = create_heleket_signature(payload, CRYPTO_API_KEY)

            # 3. Добавляем подпись в payload для отправки
            payload["sign"] = signature
            
            headers = {"Content-Type": "application/json"}
            api_url = "https://api.heleket.com/v1/payment"
            
            # Отладочный вывод финального payload перед отправкой
            # logger.info(f"Sending payload to Heleket: {payload}")
            
            async with session.post(api_url, json=payload, headers=headers) as response:
                response_text = await response.text()
                
                if response.status == 201:
                    data = json.loads(response_text)
                    payment_url = data.get("pay_url")
                    
                    if not payment_url:
                        logger.error(f"Heleket API success, but no pay_url in response: {response_text}")
                        await callback.message.edit_text("❌ Ошибка получения ссылки на оплату.")
                        return

                    await callback.message.edit_text(
                        "✅ Счет создан!\n\nНажмите на кнопку ниже для оплаты криптовалютой:",
                        reply_markup=keyboards.create_payment_keyboard(payment_url)
                    )
                else:
                    logger.error(f"Heleket API error: {response.status} - {response_text}")
                    await callback.message.edit_text("❌ Не удалось создать счет для оплаты криптовалютой.")

    except Exception as e:
        logger.error(f"Exception during crypto payment creation: {e}", exc_info=True)
        await callback.message.edit_text("❌ Произошла критическая ошибка. Попробуйте позже.")

async def process_successful_payment(bot: Bot, metadata: dict):
    user_id, months, price, action, key_id = map(metadata.get, ['user_id', 'months', 'price', 'action', 'key_id'])
    user_id, months, price, key_id = int(user_id), int(months), float(price), int(key_id)
    chat_id_to_delete = metadata.get('chat_id')
    message_id_to_delete = metadata.get('message_id')
    
    if chat_id_to_delete and message_id_to_delete:
        try:
            await bot.delete_message(chat_id=chat_id_to_delete, message_id=message_id_to_delete)
        except TelegramBadRequest as e:
            logger.warning(f"Could not delete payment message: {e}")

    processing_message = await bot.send_message(chat_id=user_id, text="✅ Оплата получена! Обрабатываю ваш запрос...")
    try:
        api, target_inbound = xui_api.login()
        if not api or not target_inbound:
            await processing_message.edit_text("❌ Ошибка на сервере.")
            return

        days_to_add = months * 30
        email = ""
        key_number = 0
        
        if action == "new":
            key_number = get_next_key_number(user_id)
            email = f"user{user_id}-key{key_number}@telegram.bot"
        elif action == "extend":
            key_data = get_key_by_id(key_id)
            if not key_data or key_data['user_id'] != user_id:
                await processing_message.edit_text("❌ Ошибка: ключ для продления не найден.")
                return
            all_user_keys = get_user_keys(user_id)
            key_number = next((i + 1 for i, key in enumerate(all_user_keys) if key['key_id'] == key_id), 0)
            email = key_data['key_email']
        
        user_uuid, new_expiry_timestamp = xui_api.update_or_create_client(api, target_inbound, email, days_to_add)
        if not user_uuid:
            await processing_message.edit_text("❌ Не удалось создать/обновить ключ в панели.")
            return

        if action == "new":
            key_id = add_new_key(user_id, user_uuid, email, new_expiry_timestamp)
        elif action == "extend":
            update_key_info(key_id, user_uuid, new_expiry_timestamp)
        
        update_user_stats(user_id, price, months)
        await processing_message.delete()
        
        connection_string = xui_api.get_connection_string(target_inbound, user_uuid, email)
        
        new_expiry_date = datetime.fromtimestamp(new_expiry_timestamp / 1000)
        final_text = get_purchase_success_text(
            action=action,
            key_number=key_number,
            expiry_date=new_expiry_date,
            connection_string=connection_string
        )
        
        await bot.send_message(
            chat_id=user_id,
            text=final_text,
            reply_markup=keyboards.create_key_info_keyboard(key_id)
        )

    except Exception as e:
        logger.error(f"Error processing payment for user {user_id}: {e}", exc_info=True)
        await processing_message.edit_text("❌ Ошибка при выдаче ключа.")

@user_router.message(F.text)
async def unknown_message_handler(message: types.Message):
    if message.text and message.text.startswith('/'):
        await message.answer("Такой команды не существует. Попробуйте /start.")
        return
        
    await message.answer("Я не понимаю эту команду. Пожалуйста, используйте кнопку '🏠 Главное меню'.")