import asyncio
import logging
from datetime import datetime, timedelta

from aiogram.utils.keyboard import InlineKeyboardBuilder
from shop_bot.bot import keyboards
from shop_bot.data_manager import database
from shop_bot.modules import xui_api

CHECK_INTERVAL_SECONDS = 300 
SUBSCRIPTION_CHECK_INTERVAL = 300

NOTIFY_BEFORE = [168,72,24,12,6,3,1]

notified_users = {}

logger = logging.getLogger(__name__)

def format_time_left(hours: int, unit: str) -> str:
    if unit == 'days':
        if hours == 1:
            return "1 день"
        elif 2 <= hours <= 4:
            return f"{hours} дня"
        else:
            return f"{hours} дней"
    else:
        if hours == 1:
            return "1 час"
        elif 2 <= hours <= 4:
            return f"{hours} часа"
        else:
            return f"{hours} часов"

async def send_subscription_notification(bot, user_id: int, time_left: int, key_info: dict, unit: str = 'days'):
    try:
        time_text = format_time_left(time_left, unit)
        
        expiry_date = None
        if isinstance(key_info['expiry_date'], (int, float)):
            expiry_date = datetime.fromtimestamp(float(key_info['expiry_date']) / 1000)
        elif isinstance(key_info['expiry_date'], str):
            expiry_date = datetime.strptime(key_info['expiry_date'].split('.')[0], '%Y-%m-%d %H:%M:%S')
        
        if not expiry_date:
            logger.error(f"Cannot determine expiry date for key {key_info.get('key_id')}")
            return
            
        expiry_str = expiry_date.strftime('%d.%m.%Y в %H:%M')
        
        message = (
            f"⚠️ *Внимание!* ⚠️\n\n"
            f"Ваша подписка истекает через *{time_text}*\n"
            f"Дата окончания: *{expiry_str}*\n\n"
            f"Продлите подписку, чтобы не остаться без доступа к VPN!"
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(keyboards.get_main_menu_button())
        builder.row(keyboards.get_buy_button())
        
        await bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
        logger.info(f"Sent subscription notification to user {user_id} - {time_left} {unit} left")
        
    except Exception as e:
        logger.error(f"Error sending subscription notification to user {user_id}: {e}")
        logger.exception("Detailed error:")

def get_days_text(days: int) -> str:
    if days % 10 == 1 and days % 100 != 11:
        return 'день'
    elif 2 <= days % 10 <= 4 and (days % 100 < 10 or days % 100 >= 20):
        return 'дня'
    return 'дней'

bot_instance = None

def init_scheduler(bot):
    global bot_instance
    bot_instance = bot

async def check_expiring_subscriptions():
    if not bot_instance:
        logger.warning("Bot instance not initialized, skipping subscription check")
        return
        
    logger.info("Starting check for expiring subscriptions...")
    
    all_hosts = database.get_all_hosts()
    current_time = datetime.now()
    
    for host in all_hosts:
        keys_in_db = database.get_keys_for_host(host['host_name'])
        
        for key in keys_in_db:
            if not key['expiry_date']:
                continue
                
            try:
                if isinstance(key['expiry_date'], (int, float)):
                    expiry_date = datetime.fromtimestamp(float(key['expiry_date']) / 1000)
                elif isinstance(key['expiry_date'], str):
                    expiry_date = datetime.strptime(key['expiry_date'].split('.')[0], '%Y-%m-%d %H:%M:%S')
                else:
                    logger.error(f"Unknown expiry_date format for key {key.get('key_id')}: {key['expiry_date']}")
                    continue
                    
                time_left = expiry_date - current_time
                total_hours_left = int(time_left.total_seconds() / 3600)
                
                logger.debug(f"Key {key.get('key_id')} expires at {expiry_date}, {total_hours_left} hours left")
                
            except Exception as e:
                logger.error(f"Error processing expiry date for key {key.get('key_id')} (value: {key.get('expiry_date')}): {e}")
                continue
            
            for hours in NOTIFY_BEFORE:
                if 0 <= total_hours_left - hours < 1:
                    user_id = key['user_id']
                    key_id = key['key_id']
                    
                    if user_id not in notified_users:
                        notified_users[user_id] = {}
                    if key_id not in notified_users[user_id]:
                        notified_users[user_id][key_id] = set()
                    
                    if hours not in notified_users[user_id][key_id]:
                        logger.info(f"Sending notification to user {user_id} - {hours} hours left")
                        await send_subscription_notification(bot_instance, user_id, hours, key, 'hours')
                        notified_users[user_id][key_id].add(hours)
                    else:
                        logger.debug(f"Notification already sent to user {user_id} for key {key_id} - {hours} hours")
                    
                    break
    
    logger.info("Finished checking expiring subscriptions")

async def periodic_subscription_check():
    logger.info("Scheduler has been started. Initial check will be in a moment.")
    await asyncio.sleep(10)
    
    last_notification_check = datetime.now() - timedelta(days=1)
    check_interval = 5

    while True:
        current_time = datetime.now()
        
        if not bot_instance:
            logger.warning("Bot instance not initialized, waiting...")
            await asyncio.sleep(check_interval)
            continue
            
        if check_interval != CHECK_INTERVAL_SECONDS:
            check_interval = CHECK_INTERVAL_SECONDS
            logger.info("Bot instance is now available, switching to normal check interval")
        
        logger.info("Scheduler: Starting periodic subscription check cycle...")
        total_affected_records = 0

        all_hosts = database.get_all_hosts()
        if not all_hosts:
            logger.info("Scheduler: No hosts configured in the database. Skipping check.")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            continue

        if (current_time - last_notification_check).total_seconds() >= SUBSCRIPTION_CHECK_INTERVAL:
            logger.info("Checking for expiring subscriptions...")
            await check_expiring_subscriptions()
            last_notification_check = current_time

        for host in all_hosts:
            host_name = host['host_name']
            logger.info(f"Scheduler: Processing host: '{host_name}'")
            
            try:
                api, inbound = xui_api.login_to_host(
                    host_url=host['host_url'],
                    username=host['host_username'],
                    password=host['host_pass'],
                    inbound_id=host['host_inbound_id']
                )

                if not api or not inbound:
                    logger.error(f"Scheduler: Could not log in to host '{host_name}'. Skipping this host.")
                    continue
                
                full_inbound_details = api.inbound.get_by_id(inbound.id)
                clients_on_server = {client.email: client for client in (full_inbound_details.settings.clients or [])}
                logger.info(f"Scheduler: Found {len(clients_on_server)} clients on the '{host_name}' panel.")

                keys_in_db = database.get_keys_for_host(host_name)
                
                for db_key in keys_in_db:
                    key_email = db_key['key_email']
                    
                    server_client = clients_on_server.pop(key_email, None)

                    if server_client:
                        server_expiry_ms = server_client.expiry_time
                        local_expiry_dt = datetime.fromisoformat(db_key['expiry_date'])
                        local_expiry_ms = int(local_expiry_dt.timestamp() * 1000)

                        if abs(server_expiry_ms - local_expiry_ms) > 1000:
                            database.update_key_status_from_server(key_email, server_client)
                            total_affected_records += 1
                            logger.info(f"Scheduler: Synced key '{key_email}' for host '{host_name}'.")
                    else:
                        logger.warning(f"Scheduler: Key '{key_email}' for host '{host_name}' not found on server. Deleting from local DB.")
                        database.update_key_status_from_server(key_email, None)
                        total_affected_records += 1

                if clients_on_server:
                    for orphan_email in clients_on_server.keys():
                        logger.warning(f"Scheduler: Found orphan client '{orphan_email}' on host '{host_name}' that is not tracked by the bot.")

            except Exception as e:
                logger.error(f"Scheduler: An unexpected error occurred while processing host '{host_name}': {e}", exc_info=True)
        
        logger.info(f"Scheduler: Cycle finished. Total records affected this cycle: {total_affected_records}.")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)