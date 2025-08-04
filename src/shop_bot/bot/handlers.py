import logging
import uuid
import qrcode
import aiohttp
import re
import aiohttp
from functools import wraps
from yookassa import Payment
from io import BytesIO
from datetime import datetime, timedelta
from aiosend import CryptoPay
from decimal import Decimal, ROUND_HALF_UP

from aiogram import Bot, Router, F, types, html
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatMemberStatus

from shop_bot.bot import keyboards
from shop_bot.modules import xui_api
from shop_bot.data_manager.database import (
    get_user, add_new_key, get_user_keys, update_user_stats,
    register_user_if_not_exists, get_next_key_number, get_key_by_id,
    update_key_info, set_trial_used, set_terms_agreed, get_setting, get_all_hosts,
    get_plans_for_host, get_plan_by_id, log_transaction
)
from shop_bot.config import (
    get_profile_text, get_vpn_active_text, VPN_INACTIVE_TEXT, VPN_NO_DATA_TEXT,
    get_key_info_text, CHOOSE_PAYMENT_METHOD_MESSAGE, get_purchase_success_text
)

TELEGRAM_BOT_USERNAME = None
PAYMENT_METHODS = None
ADMIN_ID = None
CRYPTO_BOT_TOKEN = get_setting("cryptobot_token")

logger = logging.getLogger(__name__)
admin_router = Router()
user_router = Router()

class KeyPurchase(StatesGroup):
    waiting_for_host_selection = State()
    waiting_for_plan_selection = State()

class Onboarding(StatesGroup):
    waiting_for_subscription_and_agreement = State()

class PaymentProcess(StatesGroup):
    waiting_for_email = State()
    waiting_for_payment_method = State()

def is_valid_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(pattern, email) is not None

async def show_main_menu(message: types.Message, edit_message: bool = False):
    user_id = message.chat.id
    user_db_data = get_user(user_id)
    user_keys = get_user_keys(user_id)
    
    trial_available = not (user_db_data and user_db_data.get('trial_used'))

    text = "🏠 <b>Главное меню</b>\n\nВыберите действие:"
    keyboard = keyboards.create_main_menu_keyboard(user_keys, trial_available)
    
    if edit_message:
        try:
            await message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest:
            pass
    else:
        await message.answer(text, reply_markup=keyboard)

def registration_required(f):
    @wraps(f)
    async def decorated_function(event: types.Update, *args, **kwargs):
        user_id = event.from_user.id
        user_data = get_user(user_id)
        if user_data:
            return await f(event, *args, **kwargs)
        else:
            message_text = "Пожалуйста, для начала работы со мной, отправьте команду /start"
            if isinstance(event, types.CallbackQuery):
                await event.answer(message_text, show_alert=True)
            else:
                await event.answer(message_text)
    return decorated_function

def get_user_router() -> Router:
    user_router = Router()

    @user_router.message(Command("start"))
    async def start_handler(message: types.Message, state: FSMContext, bot: Bot):
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
            return

        terms_url = get_setting("terms_url")
        privacy_url = get_setting("privacy_url")
        channel_url = get_setting("channel_url")

        if not channel_url and (not terms_url or not privacy_url):
            set_terms_agreed(user_id)
            await show_main_menu(message)
            return

        welcome_parts = ["<b>Добро пожаловать!</b>\n"]
        if channel_url:
            welcome_parts.append("Для доступа ко всем функциям, пожалуйста, подпишитесь на наш канал.")
        if terms_url and privacy_url:
            welcome_parts.append(
                "Также необходимо ознакомиться и принять наши "
                f"<a href='{terms_url}'>Условия использования</a> и "
                f"<a href='{privacy_url}'>Политику конфиденциальности</a>."
            )
        
        welcome_parts.append("\nПосле этого нажмите кнопку ниже.")
        final_text = "\n".join(welcome_parts)
        
        await message.answer(
            final_text,
            reply_markup=keyboards.create_welcome_keyboard(channel_url),
            disable_web_page_preview=True
        )
        await state.set_state(Onboarding.waiting_for_subscription_and_agreement)

    @user_router.callback_query(Onboarding.waiting_for_subscription_and_agreement, F.data == "check_subscription_and_agree")
    async def check_subscription_handler(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
        user_id = callback.from_user.id
        channel_url = get_setting("channel_url")

        if not channel_url:
            await process_successful_onboarding(callback, state)
            return
            
        try:
            if '@' not in channel_url and 't.me/' not in channel_url:
                 logger.error(f"Неверный формат URL канала: {channel_url}. Пропускаем проверку подписки.")
                 await process_successful_onboarding(callback, state)
                 return

            channel_id = '@' + channel_url.split('/')[-1] if 't.me/' in channel_url else channel_url
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            
            if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                await process_successful_onboarding(callback, state)
            else:
                await callback.answer("Вы еще не подписались на канал. Пожалуйста, подпишитесь и попробуйте снова.", show_alert=True)

        except Exception as e:
            logger.error(f"Ошибка при проверке подписки для user_id {user_id} на канал {channel_url}: {e}")
            await callback.answer("Не удалось проверить подписку. Убедитесь, что бот является администратором канала. Попробуйте позже.", show_alert=True)

    @user_router.message(Onboarding.waiting_for_subscription_and_agreement)
    async def onboarding_fallback_handler(message: types.Message):
        await message.answer("Пожалуйста, выполните требуемые действия и нажмите на кнопку в сообщении выше.")

    @user_router.message(F.text == "🏠 Главное меню")
    @registration_required
    async def main_menu_handler(message: types.Message):
        await show_main_menu(message)

    @user_router.callback_query(F.data == "back_to_main_menu")
    @registration_required
    async def back_to_main_menu_handler(callback: types.CallbackQuery):
        await callback.answer()
        await show_main_menu(callback.message, edit_message=True)

    @user_router.callback_query(F.data == "show_profile")
    @registration_required
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
    @registration_required
    async def about_handler(callback: types.CallbackQuery):
        await callback.answer()
        
        about_text = get_setting("about_text")
        terms_url = get_setting("terms_url")
        privacy_url = get_setting("privacy_url")
        channel_url = get_setting("channel_url")

        final_text = about_text if about_text else "Информация о проекте не добавлена."

        keyboard = keyboards.create_about_keyboard(channel_url, terms_url, privacy_url)

        await callback.message.edit_text(
            final_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

    @user_router.callback_query(F.data == "show_help")
    @registration_required
    async def about_handler(callback: types.CallbackQuery):
        await callback.answer()

        support_user = get_setting("support_user")
        support_text = get_setting("support_text")

        if support_user == None and support_text == None:
            await callback.message.edit_text(
                "Информация о поддержке не установлена. Установите её в админ-панели.",
                reply_markup=keyboards.create_back_to_menu_keyboard()
            )
        elif support_text == None:
            await callback.message.edit_text(
                "Для связи с поддержкой используйте кнопку ниже.",
                reply_markup=keyboards.create_support_keyboard(support_user)
            )
        else:
            await callback.message.edit_text(
                support_text + "\n\n",
                reply_markup=keyboards.create_support_keyboard(support_user)
            )

    @user_router.callback_query(F.data == "manage_keys")
    @registration_required
    async def manage_keys_handler(callback: types.CallbackQuery):
        await callback.answer()
        user_id = callback.from_user.id
        user_keys = get_user_keys(user_id)
        await callback.message.edit_text(
            "Ваши ключи:" if user_keys else "У вас пока нет ключей, давайте создадим первый!",
            reply_markup=keyboards.create_keys_management_keyboard(user_keys)
        )

    @user_router.callback_query(F.data == "get_trial")
    @registration_required
    async def trial_period_handler(callback: types.CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        user_db_data = get_user(user_id)
        if user_db_data and user_db_data.get('trial_used'):
            await callback.answer("Вы уже использовали бесплатный пробный период.", show_alert=True)
            return

        hosts = get_all_hosts()
        if not hosts:
            await callback.message.edit_text("❌ В данный момент нет доступных серверов для создания пробного ключа.")
            return
            
        if len(hosts) == 1:
            await callback.answer()
            await process_trial_key_creation(callback.message, hosts[0]['host_name'])
        else:
            await callback.answer()
            await callback.message.edit_text(
                "Выберите сервер, на котором хотите получить пробный ключ:",
                reply_markup=keyboards.create_host_selection_keyboard(hosts, action="trial")
            )

    @user_router.callback_query(F.data.startswith("select_host_trial_"))
    @registration_required
    async def trial_host_selection_handler(callback: types.CallbackQuery):
        await callback.answer()
        host_name = callback.data[len("select_host_trial_"):]
        await process_trial_key_creation(callback.message, host_name)

    async def process_trial_key_creation(message: types.Message, host_name: str):
        user_id = message.chat.id
        await message.edit_text(f"Отлично! Создаю для вас бесплатный ключ на 3 дня на сервере \"{host_name}\"...")
        
        try:
            result = await xui_api.create_or_update_key_on_host(
                host_name=host_name,
                email=f"user{user_id}-key{get_next_key_number(user_id)}-trial@telegram.bot",
                days_to_add=3
            )
            if not result:
                await message.edit_text("❌ Не удалось создать пробный ключ. Ошибка на сервере.")
                return

            set_trial_used(user_id)
            
            new_key_id = add_new_key(
                user_id=user_id,
                host_name=host_name,
                xui_client_uuid=result['client_uuid'],
                key_email=result['email'],
                expiry_timestamp_ms=result['expiry_timestamp_ms']
            )
            
            await message.delete()
            new_expiry_date = datetime.fromtimestamp(result['expiry_timestamp_ms'] / 1000)
            final_text = get_purchase_success_text("готов", get_next_key_number(user_id) -1, new_expiry_date, result['connection_string'])
            await message.answer(text=final_text, reply_markup=keyboards.create_key_info_keyboard(new_key_id))

        except Exception as e:
            logger.error(f"Error creating trial key for user {user_id} on host {host_name}: {e}", exc_info=True)
            await message.edit_text("❌ Произошла ошибка при создании пробного ключа.")

    @user_router.callback_query(F.data.startswith("show_key_"))
    @registration_required
    async def show_key_handler(callback: types.CallbackQuery):
        key_id_to_show = int(callback.data.split("_")[2])
        await callback.message.edit_text("Загружаю информацию о ключе...")
        user_id = callback.from_user.id
        key_data = get_key_by_id(key_id_to_show)

        if not key_data or key_data['user_id'] != user_id:
            await callback.message.edit_text("❌ Ошибка: ключ не найден.")
            return
            
        try:
            details = await xui_api.get_key_details_from_host(key_data)
            if not details or not details['connection_string']:
                await callback.message.edit_text("❌ Ошибка на сервере. Не удалось получить данные ключа.")
                return

            connection_string = details['connection_string']
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
    @registration_required
    async def show_qr_handler(callback: types.CallbackQuery):
        await callback.answer("Генерирую QR-код...")
        key_id = int(callback.data.split("_")[2])
        key_data = get_key_by_id(key_id)
        if not key_data or key_data['user_id'] != callback.from_user.id: return
        
        try:
            details = await xui_api.get_key_details_from_host(key_data)
            if not details or not details['connection_string']:
                await callback.answer("Ошибка: Не удалось сгенерировать QR-код.", show_alert=True)
                return

            connection_string = details['connection_string']
            qr_img = qrcode.make(connection_string)
            bio = BytesIO(); qr_img.save(bio, "PNG"); bio.seek(0)
            qr_code_file = BufferedInputFile(bio.read(), filename="vpn_qr.png")
            await callback.message.answer_photo(photo=qr_code_file)
        except Exception as e:
            logger.error(f"Error showing QR for key {key_id}: {e}")

    @user_router.callback_query(F.data.startswith("show_instruction_"))
    @registration_required
    async def show_instruction_handler(callback: types.CallbackQuery):
        await callback.answer()
        key_id = int(callback.data.split("_")[2])

        instruction_text = (
            "<b>Как подключиться?</b>\n\n"
            "1. Скопируйте ключ подключения `vless://...`\\.\n"
            "2. Скачайте приложение, совместимое с Xray/V2Ray:\n"
            "   - <b>Android:</b> V2RayTUN https://play.google.com/store/apps/details?id=com.v2raytun.android&hl=ru\n"
            "   - <b>iOS:</b> V2RayTUN https://apps.apple.com/us/app/v2raytun/id6476628951?platform=iphone\n"
            "   - <b>Windows/Linux:</b> Nekoray 3.26 https://github.com/MatsuriDayo/nekoray/releases/tag/3.26\n"
            "3. Посмотреть и полностью прочитать туториал по использованию ключей можно на: https://web.archive.org/web/20250622005028/https://wiki.aeza.net/nekoray-universal-client.\n"
        )
        
        await callback.message.edit_text(
            instruction_text,
            reply_markup=keyboards.create_back_to_key_keyboard(key_id),
            disable_web_page_preview=True
        )

    @user_router.callback_query(F.data == "buy_new_key")
    @registration_required
    async def buy_new_key_handler(callback: types.CallbackQuery):
        await callback.answer()
        hosts = get_all_hosts()
        if not hosts:
            await callback.message.edit_text("❌ В данный момент нет доступных серверов для покупки.")
            return
        
        await callback.message.edit_text(
            "Выберите сервер, на котором хотите приобрести ключ:",
            reply_markup=keyboards.create_host_selection_keyboard(hosts, action="new")
        )

    @user_router.callback_query(F.data.startswith("select_host_new_"))
    @registration_required
    async def select_host_for_purchase_handler(callback: types.CallbackQuery):
        await callback.answer()
        host_name = callback.data[len("select_host_new_"):]
        plans = get_plans_for_host(host_name)
        if not plans:
            await callback.message.edit_text(f"❌ Для сервера \"{host_name}\" не настроены тарифы.")
            return
        await callback.message.edit_text(
            "Выберите тариф для нового ключа:", 
            reply_markup=keyboards.create_plans_keyboard(plans, action="new", host_name=host_name)
        )

    @user_router.callback_query(F.data.startswith("extend_key_"))
    @registration_required
    async def extend_key_handler(callback: types.CallbackQuery):
        await callback.answer()

        try:
            key_id = int(callback.data.split("_")[2])
        except (IndexError, ValueError):
            await callback.message.edit_text("❌ Произошла ошибка. Неверный формат ключа.")
            return

        key_data = get_key_by_id(key_id)

        if not key_data or key_data['user_id'] != callback.from_user.id:
            await callback.message.edit_text("❌ Ошибка: Ключ не найден или не принадлежит вам.")
            return
        
        host_name = key_data.get('host_name')
        if not host_name:
            await callback.message.edit_text("❌ Ошибка: У этого ключа не указан сервер. Обратитесь в поддержку.")
            return

        plans = get_plans_for_host(host_name)

        if not plans:
            await callback.message.edit_text(
                f"❌ Извините, для сервера \"{host_name}\" в данный момент не настроены тарифы для продления."
            )
            return

        await callback.message.edit_text(
            f"Выберите тариф для продления ключа на сервере \"{host_name}\":",
            reply_markup=keyboards.create_plans_keyboard(
                plans=plans,
                action="extend",
                host_name=host_name,
                key_id=key_id
            )
        )

    @user_router.callback_query(F.data.startswith("buy_"))
    @registration_required
    async def plan_selection_handler(callback: types.CallbackQuery, state: FSMContext):
        await callback.answer()
        
        parts = callback.data.split("_")[1:]
        action = parts[-2]
        key_id = int(parts[-1])
        plan_id = int(parts[-3])
        host_name = "_".join(parts[:-3])

        await state.update_data(
            action=action, key_id=key_id, plan_id=plan_id, host_name=host_name
        )
        
        await callback.message.edit_text(
            "📧 Пожалуйста, введите ваш email для отправки чека об оплате.\n\n"
            "Если вы не хотите указывать почту, нажмите кнопку ниже.",
            reply_markup=keyboards.create_skip_email_keyboard()
        )
        await state.set_state(PaymentProcess.waiting_for_email)

    @user_router.callback_query(PaymentProcess.waiting_for_email, F.data == "back_to_plans")
    async def back_to_plans_handler(callback: types.CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await state.clear()
        
        action = data.get('action')
        if action == 'new':
            await buy_new_key_handler(callback)
        elif action == 'extend':
            callback.data = f"extend_key_{data.get('key_id', 0)}"
            await extend_key_handler(callback)
        else:
            await back_to_main_menu_handler(callback)

    @user_router.message(PaymentProcess.waiting_for_email)
    async def process_email_handler(message: types.Message, state: FSMContext):
        if is_valid_email(message.text):
            await state.update_data(customer_email=message.text)
            await message.answer(f"✅ Email принят: {message.text}")
            await show_payment_options(message, state)
        else:
            await message.answer("❌ Неверный формат email. Попробуйте еще раз.")

    @user_router.callback_query(PaymentProcess.waiting_for_email, F.data == "skip_email")
    async def skip_email_handler(callback: types.CallbackQuery, state: FSMContext):
        await callback.answer()
        await state.update_data(customer_email=None)
        await show_payment_options(callback.message, state)

    async def show_payment_options(message: types.Message, state: FSMContext):
        data = await state.get_data()
        
        try:
            await message.edit_text(
                CHOOSE_PAYMENT_METHOD_MESSAGE,
                reply_markup=keyboards.create_payment_method_keyboard(
                    payment_methods=PAYMENT_METHODS,
                    action=data.get('action'),
                    key_id=data.get('key_id')
                )
            )
        except TelegramBadRequest:
            await message.answer(
                CHOOSE_PAYMENT_METHOD_MESSAGE,
                reply_markup=keyboards.create_payment_method_keyboard(
                    payment_methods=PAYMENT_METHODS,
                    action=data.get('action'),
                    key_id=data.get('key_id')
                )
            )
        await state.set_state(PaymentProcess.waiting_for_payment_method)
        
    @user_router.callback_query(PaymentProcess.waiting_for_payment_method, F.data == "back_to_email_prompt")
    async def back_to_email_prompt_handler(callback: types.CallbackQuery, state: FSMContext):
        await callback.message.edit_text(
            "📧 Пожалуйста, введите ваш email для отправки чека об оплате.\n\n"
            "Если вы не хотите указывать почту, нажмите кнопку ниже.",
            reply_markup=keyboards.create_skip_email_keyboard()
        )
        await state.set_state(PaymentProcess.waiting_for_email)


    @user_router.callback_query(PaymentProcess.waiting_for_payment_method, F.data == "pay_yookassa")
    async def create_yookassa_payment_handler(callback: types.CallbackQuery, state: FSMContext):
        await callback.answer("Создаю ссылку на оплату...")
        
        data = await state.get_data()
        
        plan_id = data.get('plan_id')
        customer_email = data.get('customer_email')
        host_name = data.get('host_name')
        action = data.get('action')
        key_id = data.get('key_id')
        
        if not customer_email:
            customer_email = get_setting("receipt_email")

        plan = get_plan_by_id(plan_id)
        if not plan:
            await callback.message.answer("Произошла ошибка при выборе тарифа.")
            await state.clear()
            return

        price_rub, months = plan['price'], plan['months']
        user_id = callback.from_user.id
        
        receipt = None
        if customer_email and is_valid_email(customer_email):
            receipt = {
                "customer": {"email": customer_email},
                "items": [{
                    "description": f"Подписка на {months} мес.",
                    "quantity": "1.00",
                    "amount": {"value": f"{price_rub:.2f}", "currency": "RUB"},
                    "vat_code": "1"
                }]
            }

        try:
            payment_payload = {
                "amount": {"value": f"{price_rub:.2f}", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": f"https://t.me/{TELEGRAM_BOT_USERNAME}"},
                "capture": True,
                "description": f"Подписка на {months} мес.",
                "metadata": {
                    "user_id": user_id, "months": months, "price": price_rub, 
                    "action": action, "key_id": key_id, "host_name": host_name,
                    "plan_id": plan_id, "customer_email": customer_email
                }
            }
            if receipt:
                payment_payload['receipt'] = receipt

            payment = Payment.create(payment_payload, uuid.uuid4())
            
            await state.clear()
            
            await callback.message.edit_text(
                "Нажмите на кнопку ниже для оплаты:",
                reply_markup=keyboards.create_payment_keyboard(payment.confirmation.confirmation_url)
            )
        except Exception as e:
            logger.error(f"Failed to create YooKassa payment: {e}", exc_info=True)
            await callback.message.answer("Не удалось создать ссылку на оплату.")
            await state.clear()

    @user_router.callback_query(PaymentProcess.waiting_for_payment_method, F.data == "pay_cryptobot")
    async def create_cryptobot_invoice_handler(callback: types.CallbackQuery, state: FSMContext):
        await callback.answer("Создаю счет в Crypto Pay...")
        
        data = await state.get_data()
        
        plan_id = data.get('plan_id')
        user_id = data.get('user_id', callback.from_user.id)
        customer_email = data.get('customer_email')
        host_name = data.get('host_name')
        action = data.get('action')
        key_id = data.get('key_id')

        cryptobot_token = get_setting('cryptobot_token')
        if not cryptobot_token:
            logger.error(f"Attempt to create Crypto Pay invoice failed for user {user_id}: cryptobot_token is not set.")
            await callback.message.edit_text("❌ Оплата криптовалютой временно недоступна. (Администратор не указал токен).")
            await state.clear()
            return

        plan = get_plan_by_id(plan_id)
        if not plan:
            logger.error(f"Attempt to create Crypto Pay invoice failed for user {user_id}: Plan with id {plan_id} not found.")
            await callback.message.edit_text("❌ Произошла ошибка при выборе тарифа.")
            await state.clear()
            return
            
        price_rub = Decimal(str(plan['price']))
        months = plan['months']
        
        try:
            exchange_rate = await get_usdt_rub_rate()

            if not exchange_rate:
                logger.warning("Failed to get live exchange rate. Falling back to the rate from settings.")
                if not exchange_rate:
                    await callback.message.edit_text("❌ Не удалось получить курс валют. Попробуйте позже.")
                    await state.clear()
                    return

            margin = Decimal("1.03")
            price_usdt = (price_rub / exchange_rate * margin).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
            logger.info(f"Creating Crypto Pay invoice for user {user_id}. Plan price: {price_rub} RUB. Converted to: {price_usdt} USDT.")

            crypto = CryptoPay(cryptobot_token)
            
            payload_data = f"{user_id}:{months}:{float(price_rub)}:{action}:{key_id}:{host_name}:{plan_id}:{customer_email}"

            invoice = await crypto.create_invoice(
                currency_type="fiat",
                fiat="RUB",
                amount=float(price_rub),
                description=f"Подписка на {months} мес.",
                payload=payload_data,
                expires_in=3600
            )
            
            if not invoice or not invoice.pay_url:
                raise Exception("Failed to create invoice or pay_url is missing.")

            await callback.message.edit_text(
                "Нажмите на кнопку ниже для оплаты:",
                reply_markup=keyboards.create_payment_keyboard(invoice.pay_url)
            )
            await state.clear()

        except Exception as e:
            logger.error(f"Failed to create Crypto Pay invoice for user {user_id}: {e}", exc_info=True)
            await callback.message.edit_text(f"❌ Не удалось создать счет для оплаты криптовалютой.\n\n<pre>Ошибка: {e}</pre>")
            await state.clear()
        
        @user_router.message(F.text)
        @registration_required
        async def unknown_message_handler(message: types.Message):
            if message.text.startswith('/'):
                await message.answer("Такой команды не существует. Попробуйте /start.")
            else:
                await message.answer("Я не понимаю эту команду. Пожалуйста, используйте кнопки меню.")
    return user_router

async def process_successful_onboarding(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("✅ Спасибо! Доступ предоставлен.")
    set_terms_agreed(callback.from_user.id)
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Приятного использования!", reply_markup=keyboards.main_reply_keyboard)
    await show_main_menu(callback.message)

async def get_usdt_rub_rate() -> Decimal | None:
    url = "https://api.binance.com/api/v3/ticker/price"
    params = {"symbol": "USDTRUB"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                price_str = data.get('price')
                if price_str:
                    logger.info(f"Got USDT RUB: {price_str}")
                    return Decimal(price_str)
                logger.error("Can't find 'price' in Binance response.")
                return None
    except Exception as e:
        logger.error(f"Error getting USDT RUB Binance rate: {e}", exc_info=True)
        return None

async def process_successful_payment(bot: Bot, metadata: dict):
    try:
        user_id = int(metadata['user_id'])
        months = int(metadata['months'])
        price = float(metadata['price'])
        action = metadata['action']
        key_id = int(metadata['key_id'])
        host_name = metadata['host_name']
        plan_id = int(metadata['plan_id'])
        customer_email = metadata.get('customer_email')

        chat_id_to_delete = metadata.get('chat_id')
        message_id_to_delete = metadata.get('message_id')
        
    except (ValueError, TypeError) as e:
        logger.error(f"FATAL: Could not parse metadata. Error: {e}. Metadata: {metadata}")
        return

    if chat_id_to_delete and message_id_to_delete:
        try:
            await bot.delete_message(chat_id=chat_id_to_delete, message_id=message_id_to_delete)
        except TelegramBadRequest as e:
            logger.warning(f"Could not delete payment message: {e}")

    processing_message = await bot.send_message(
        chat_id=user_id,
        text=f"✅ Оплата получена! Обрабатываю ваш запрос на сервере \"{host_name}\"..."
    )
    try:
        email = ""
        if action == "new":
            key_number = get_next_key_number(user_id)
            email = f"user{user_id}-key{key_number}@{host_name.replace(' ', '').lower()}.bot"
        elif action == "extend":
            key_data = get_key_by_id(key_id)
            if not key_data or key_data['user_id'] != user_id:
                await processing_message.edit_text("❌ Ошибка: ключ для продления не найден.")
                return
            email = key_data['key_email']
        
        days_to_add = months * 30
        result = await xui_api.create_or_update_key_on_host(
            host_name=host_name,
            email=email,
            days_to_add=days_to_add
        )

        if not result:
            await processing_message.edit_text("❌ Не удалось создать/обновить ключ в панели.")
            return

        if action == "new":
            key_id = add_new_key(user_id, host_name, result['client_uuid'], result['email'], result['expiry_timestamp_ms'])
        elif action == "extend":
            update_key_info(key_id, result['client_uuid'], result['expiry_timestamp_ms'])
        
        update_user_stats(user_id, price, months)
        
        user_info = get_user(user_id)
        plan_info = get_plan_by_id(plan_id)
        log_transaction(
            user_id=user_id,
            username=user_info.get('username', 'N/A') if user_info else 'N/A',
            email=customer_email,
            host_name=host_name,
            plan_name=plan_info.get('plan_name', 'Неизвестный') if plan_info else 'Неизвестный',
            months=months,
            amount=price,
            method='Crypto' if 'chat_id' not in metadata else 'YooKassa'
        )
        
        await processing_message.delete()
        
        connection_string = result['connection_string']
        new_expiry_date = datetime.fromtimestamp(result['expiry_timestamp_ms'] / 1000)
        
        all_user_keys = get_user_keys(user_id)
        key_number = next((i + 1 for i, key in enumerate(all_user_keys) if key['key_id'] == key_id), len(all_user_keys))

        final_text = get_purchase_success_text(
            action="создан" if action == "new" else "продлен",
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
        logger.error(f"Error processing payment for user {user_id} on host {host_name}: {e}", exc_info=True)
        await processing_message.edit_text("❌ Ошибка при выдаче ключа.")