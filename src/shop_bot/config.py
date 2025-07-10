PLANS = {
    "buy_1_month": ("1 месяц", "50.00", 1),
    "buy_3_months": ("3 месяца", "135.00", 3),
    "buy_6_months": ("6 месяцев", "240.00", 6),
    "buy_12_months": ("12 месяцев", "450.00", 12),
}

WELCOME_MESSAGE = "Здесь вы можете приобрести быстрый и надежный VPN."
CHOOSE_PLAN_MESSAGE = "Выберите подходящий тариф:"
CHOOSE_PAYMENT_METHOD_MESSAGE = "Выберите удобный способ оплаты:"

def get_profile_text(username, total_spent, total_months, vpn_status_text):
    return (
        f"👤 <b>Профиль:</b> {username}\n\n"
        f"💰 <b>Потрачено всего:</b> {total_spent:.0f} RUB\n"
        f"📅 <b>Приобретено месяцев:</b> {total_months}\n\n"
        f"{vpn_status_text}"
    )

def get_vpn_active_text(days_left, hours_left):
    return (
        f"✅ <b>Статус VPN:</b> Активен\n"
        f"⏳ <b>Осталось:</b> {days_left} д. {hours_left} ч."
    )

VPN_INACTIVE_TEXT = "❌ <b>Статус VPN:</b> Неактивен (срок истек)"
VPN_NO_DATA_TEXT = "ℹ️ <b>Статус VPN:</b> У вас пока нет активных ключей."

def get_key_info_text(key_number, expiry_date, created_date, connection_string):
    expiry_formatted = expiry_date.strftime('%d.%m.%Y в %H:%M')
    created_formatted = created_date.strftime('%d.%m.%Y в %H:%M')
    
    return (
        f"<b>🔑 Информация о ключе #{key_number}</b>\n\n"
        f"➕ <b>Приобретён:</b> {created_formatted}\n"
        f"⏳ <b>Действителен до:</b> {expiry_formatted}\n\n"
        f"<code>{connection_string}</code>"
    )

def get_purchase_success_text(action: str, key_number: int, expiry_date, connection_string: str):
    """Шаблон для сообщения после успешной покупки/продления."""
    
    action_text = "обновлен" if action == "extend" else "готов"
    expiry_formatted = expiry_date.strftime('%d.%m.%Y в %H:%M')

    return (
        f"🎉 <b>Ваш ключ #{key_number} {action_text}!</b>\n\n"
        f"⏳ <b>Он будет действовать до:</b> {expiry_formatted}\n\n"
        f"<code>{connection_string}</code>"
    )