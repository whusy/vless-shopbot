from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛒 Купить/Продлить VPN")],
        [KeyboardButton(text="👤 Мой профиль")]
    ],
    resize_keyboard=True
)

def create_plans_keyboard(plans: dict, action: str, key_id: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan_id, (name, price_rub, _) in plans.items():
        callback_data = f"{plan_id}_{action}_{key_id}"
        builder.button(text=f"{name} - {float(price_rub):.0f} RUB", callback_data=callback_data)
    builder.adjust(1)
    return builder.as_markup()

def create_payment_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Перейти к оплате", url=payment_url)
    return builder.as_markup()

def create_keys_management_keyboard(keys: list) -> InlineKeyboardMarkup:
    """Создает клавиатуру для управления ключами."""
    builder = InlineKeyboardBuilder()
    if keys:
        for i, key in enumerate(keys):
            expiry_date = datetime.fromisoformat(key['expiry_date'])
            status_icon = "✅" if expiry_date > datetime.now() else "❌"
            
            builder.button(
                text=f"{status_icon} Ключ #{i+1} (Продлить)",
                callback_data=f"extend_key_{key['key_id']}"
            )
            builder.button(
                text="Показать ℹ️",
                callback_data=f"show_key_{key['key_id']}"
            )
    
    builder.button(text="➕ Купить новый ключ", callback_data="buy_new_key")
    
    key_buttons_layout = [2] * len(keys)
    builder.adjust(*key_buttons_layout, 1)
    
    return builder.as_markup()