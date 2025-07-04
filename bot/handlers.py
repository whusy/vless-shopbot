import logging
import uuid
from io import BytesIO
from datetime import datetime, timedelta
import qrcode
from yookassa import Payment
from aiogram import Bot, Dispatcher, F, types, html
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

from . import keyboards
import modules.xui_api as xui_api
from data_manager.database import (
    get_user, add_new_key, get_user_keys, update_user_stats,
    register_user_if_not_exists, get_next_key_number, get_key_by_id, update_key_info
)
from config import (
    PLANS, CHOOSE_PLAN_MESSAGE, WELCOME_MESSAGE, 
    get_profile_text, get_vpn_active_text, VPN_INACTIVE_TEXT, VPN_NO_DATA_TEXT
)

TELEGRAM_BOT_USERNAME = None
logger = logging.getLogger(__name__)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Регистрирует пользователя, отправляет приветствие и вызывает профиль."""
    register_user_if_not_exists(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(
        f"👋 Привет, {html.bold(message.from_user.full_name)}!\n\n{WELCOME_MESSAGE}",
        reply_markup=keyboards.main_keyboard
    )
    await profile_handler(message)

@dp.message(F.text == "👤 Мой профиль")
async def profile_handler(message: types.Message):
    """Показывает ТОЛЬКО статистику пользователя."""
    user_id = message.from_user.id
    user_db_data = get_user(user_id)
    user_keys = get_user_keys(user_id)
    
    if not user_db_data:
        await message.answer("Не удалось получить данные профиля. Попробуйте нажать /start.")
        return

    username = html.bold(user_db_data.get('username', 'Пользователь'))
    total_spent = user_db_data.get('total_spent', 0)
    total_months = user_db_data.get('total_months', 0)
    active_keys_count = sum(1 for key in user_keys if datetime.fromisoformat(key['expiry_date']) > datetime.now())
    vpn_status_text = f"🔑 <b>Ключей активно:</b> {active_keys_count} из {len(user_keys)}"
    
    final_text = get_profile_text(username, total_spent, total_months, vpn_status_text)
    await message.answer(final_text)

@dp.message(F.text == "🛒 Купить/Продлить VPN")
async def buy_or_extend_handler(message: types.Message):
    """Показывает меню управления ключами."""
    user_id = message.from_user.id
    user_keys = get_user_keys(user_id)

    await message.answer(
        "Ваши ключи:",
        reply_markup=keyboards.create_keys_management_keyboard(user_keys)
    )

@dp.callback_query(F.data.startswith("show_key_"))
async def show_key_handler(callback: types.CallbackQuery):
    """Отправляет пользователю его ключ и QR-код."""
    await callback.answer("Загружаю информацию о ключе...")
    try:
        key_id_to_show = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка: неверный формат данных ключа.", show_alert=True)
        return
        
    user_id = callback.from_user.id
    
    key_data = get_key_by_id(key_id_to_show)

    if not key_data or key_data['user_id'] != user_id:
        await callback.message.answer("❌ Ошибка: ключ не найден или не принадлежит вам.")
        return

    try:
        api, target_inbound = xui_api.login()
        if not api or not target_inbound:
            await callback.message.answer("❌ Ошибка на сервере. Не удалось подключиться к панели.")
            return

        user_uuid = key_data['xui_client_uuid']
        email = key_data['key_email']
        
        connection_string = xui_api.get_connection_string(target_inbound, user_uuid, email)
        if not connection_string:
            await callback.message.answer("❌ Не удалось сгенерировать строку подключения.")
            return

        qr_img = qrcode.make(connection_string)
        bio = BytesIO(); qr_img.save(bio, "PNG"); bio.seek(0)
        qr_code_file = BufferedInputFile(bio.read(), filename="vpn_qr.png")
        
        expiry_date = datetime.fromisoformat(key_data['expiry_date'])
        caption = f"Информация о ключе (действителен до {expiry_date.strftime('%d.%m.%Y %H:%M')})"

        await callback.message.answer_photo(
            photo=qr_code_file,
            caption=caption
        )
        await callback.message.answer(f"Ваш ключ: {html.code(connection_string)}")
        
    except Exception as e:
        logger.error(f"Error showing key {key_id_to_show} for user {user_id}: {e}", exc_info=True)
        await callback.message.answer("❌ Произошла ошибка при получении данных ключа.")


@dp.callback_query(F.data == "buy_new_key")
async def buy_new_key_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "Выберите тариф для нового ключа:",
        reply_markup=keyboards.create_plans_keyboard(PLANS, action="new")
    )

@dp.callback_query(F.data.startswith("extend_key_"))
async def extend_key_handler(callback: types.CallbackQuery):
    key_id_to_extend = int(callback.data.split("_")[2])
    await callback.answer()
    await callback.message.edit_text(
        f"Выберите тариф для продления ключа:",
        reply_markup=keyboards.create_plans_keyboard(PLANS, action="extend", key_id=key_id_to_extend)
    )

@dp.callback_query(F.data.startswith("buy_") & F.data.contains("_month"))
async def create_payment_handler(callback: types.CallbackQuery):
    await callback.answer("Создаю ссылку на оплату...")
    parts = callback.data.split("_")
    plan_id = "_".join(parts[:-2]) 
    action = parts[-2]
    key_id = int(parts[-1])
    if plan_id not in PLANS:
        await callback.message.answer("Произошла ошибка при выборе тарифа.")
        return
    name, price_rub, months = PLANS[plan_id]
    user_id = callback.from_user.id
    try:
        payment = Payment.create({
            "amount": {"value": price_rub, "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": f"https://t.me/{TELEGRAM_BOT_USERNAME}"},
            "capture": True, "description": f"Оплата подписки NNVPN ({name})",
            "metadata": {"user_id": user_id, "months": months, "price": price_rub, "action": action, "key_id": key_id}
        }, uuid.uuid4())
        await callback.message.edit_text(
            "Нажмите на кнопку ниже, чтобы перейти к оплате:",
            reply_markup=keyboards.create_payment_keyboard(payment.confirmation.confirmation_url)
        )
    except Exception as e:
        logger.error(f"Failed to create YooKassa payment: {e}")
        await callback.message.answer("Не удалось создать ссылку на оплату.")

async def process_successful_payment(bot: Bot, metadata: dict):
    user_id = int(metadata['user_id'])
    months = int(metadata['months'])
    price = float(metadata['price'])
    action = metadata['action']
    key_id = int(metadata['key_id'])
    
    await bot.send_message(chat_id=user_id, text="✅ Оплата получена! Обрабатываю ваш запрос...")
    try:
        api, target_inbound = xui_api.login()
        if not api or not target_inbound:
            await bot.send_message(user_id, "❌ Ошибка на сервере. Свяжитесь с поддержкой.")
            return
        
        days_to_add = months * 30
        email = ""
        
        if action == "new":
            key_number = get_next_key_number(user_id)
            email = f"user{user_id}-key{key_number}@telegram.bot"
        elif action == "extend":
            key_data = get_key_by_id(key_id)
            if not key_data or key_data['user_id'] != user_id:
                await bot.send_message(user_id, "❌ Ошибка: ключ не найден или не принадлежит вам.")
                return
            email = key_data['key_email']
        
        user_uuid, new_expiry_timestamp = xui_api.update_or_create_client(api, target_inbound, email, days_to_add)
        if not user_uuid:
            await bot.send_message(user_id, "❌ Не удалось создать/обновить ключ в панели.")
            return

        if action == "new":
            add_new_key(user_id, user_uuid, email, new_expiry_timestamp)
        elif action == "extend":
            update_key_info(key_id, user_uuid, new_expiry_timestamp)
            
        update_user_stats(user_id, price, months)
        
        connection_string = xui_api.get_connection_string(target_inbound, user_uuid, email)
        qr_img = qrcode.make(connection_string)
        bio = BytesIO(); qr_img.save(bio, "PNG"); bio.seek(0)
        qr_code_file = BufferedInputFile(bio.read(), filename="vpn_qr.png")
        await bot.send_photo(user_id, photo=qr_code_file, caption="🎉 Ваш VPN ключ готов/обновлен!")
        await bot.send_message(user_id, f"Ваш ключ: {html.code(connection_string)}")

    except Exception as e:
        logger.error(f"Error processing payment for user {user_id}: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Ошибка при выдаче ключа. Свяжитесь с поддержкой.")