from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

main_reply_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🏠 Главное меню")]],
    resize_keyboard=True
)

def create_main_menu_keyboard(user_keys: list, trial_available: bool, is_admin: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.button(text="👤 Мой профиль", callback_data="show_profile")
    builder.button(text=f"🔑 Мои ключи ({len(user_keys)})", callback_data="manage_keys")
    
    if trial_available:
        builder.button(text="🎁 Попробовать бесплатно (3 дня)", callback_data="get_trial")
    
    builder.button(text="ℹ️ О проекте", callback_data="show_about")
    
    if is_admin:
        builder.button(text="⚙️ Админ-панель", callback_data="open_admin_panel")

    layout = [2, 1 if trial_available else 0, 1, 1 if is_admin else 0]
    actual_layout = [size for size in layout if size > 0]
    builder.adjust(*actual_layout)
    
    return builder.as_markup()

def create_admin_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Изменить 'О проекте'", callback_data="admin_edit_about")
    builder.button(text="📄 Изменить ссылку 'Условия'", callback_data="admin_edit_terms")
    builder.button(text="🔒 Изменить ссылку 'Политика'", callback_data="admin_edit_privacy")
    builder.button(text="⬅️ Выйти из админ. режима", callback_data="admin_exit")
    builder.adjust(1)
    return builder.as_markup()

def create_admin_cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin_cancel_edit")
    return builder.as_markup()

def create_about_keyboard(terms_url: str, privacy_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 Условия использования", url=terms_url)
    builder.button(text="🔒 Политика конфиденциальности", url=privacy_url)
    builder.button(text="⬅️ Назад в меню", callback_data="back_to_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def create_plans_keyboard(plans: dict, action: str, key_id: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan_id, (name, price_rub, _) in plans.items():
        callback_data = f"{plan_id}_{action}_{key_id}"
        builder.button(text=f"{name} - {float(price_rub):.0f} RUB", callback_data=callback_data)
    builder.button(text="⬅️ Назад к списку ключей", callback_data="manage_keys")
    builder.adjust(1) 
    return builder.as_markup()

def create_payment_method_keyboard(payment_methods: dict, plan_id: str, action: str, key_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if payment_methods.get("yookassa"):
        callback_data = f"pay_yookassa_{plan_id}_{action}_{key_id}"
        builder.button(text="💳 Карта / СБП (YooKassa)", callback_data=callback_data)
    if payment_methods.get("crypto"):
        callback_data = f"pay_crypto_{plan_id}_{action}_{key_id}"
        builder.button(text="💎 Криптовалюта", callback_data=callback_data)
    if action == "new":
        builder.button(text="⬅️ Назад к тарифам", callback_data="buy_new_key")
    else:
        builder.button(text="⬅️ Назад к тарифам", callback_data=f"extend_key_{key_id}")
    builder.adjust(1)
    return builder.as_markup()

def create_payment_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Перейти к оплате", url=payment_url)
    return builder.as_markup()

def create_keys_management_keyboard(keys: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if keys:
        for i, key in enumerate(keys):
            expiry_date = datetime.fromisoformat(key['expiry_date'])
            status_icon = "✅" if expiry_date > datetime.now() else "❌"
            builder.button(
                text=f"{status_icon} Ключ #{i+1} (до {expiry_date.strftime('%d.%m.%Y')})",
                callback_data=f"show_key_{key['key_id']}"
            )
    builder.button(text="➕ Купить новый ключ", callback_data="buy_new_key")
    builder.button(text="⬅️ Назад в меню", callback_data="back_to_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def create_key_info_keyboard(key_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Продлить этот ключ", callback_data=f"extend_key_{key_id}")
    builder.button(text="📱 Показать QR-код", callback_data=f"show_qr_{key_id}")
    builder.button(text="📖 Инструкция", callback_data=f"show_instruction_{key_id}")
    builder.button(text="⬅️ Назад к списку ключей", callback_data="manage_keys")
    builder.adjust(1)
    return builder.as_markup()

def create_back_to_key_keyboard(key_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад к ключу", callback_data=f"show_key_{key_id}")
    return builder.as_markup()

def create_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад в меню", callback_data="back_to_main_menu")
    return builder.as_markup()

def create_agreement_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принимаю", callback_data="agree_to_terms")
    return builder.as_markup()