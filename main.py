import logging
import os
import threading
import asyncio
from dotenv import load_dotenv

from yookassa import Configuration
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot import handlers
from webhook_server.app import create_webhook_app
from config import PLANS
from data_manager.scheduler import periodic_subscription_check
from data_manager import database

def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)


    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME")
    YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
    YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

    if not all([TELEGRAM_TOKEN, YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, TELEGRAM_BOT_USERNAME]):
        raise ValueError("Необходимо установить все переменные окружения в .env файле")

    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY
    
    handlers.PLANS = PLANS
    handlers.TELEGRAM_BOT_USERNAME = TELEGRAM_BOT_USERNAME
    
    bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = handlers.dp

    database.initialize_db()

    flask_app = create_webhook_app(bot, handlers.process_successful_payment)

    async def start_all():
        loop = asyncio.get_running_loop()
        flask_app.config['EVENT_LOOP'] = loop
        
        flask_thread = threading.Thread(
            target=lambda: flask_app.run(host='0.0.0.0', port=1488, use_reloader=False),
            daemon=True
        )
        flask_thread.start()
        logger.info("Flask server started on port 1488.")

        asyncio.create_task(periodic_subscription_check())

        logger.info("Aiogram Bot polling started...")
        await dp.start_polling(bot)

    try:
        asyncio.run(start_all())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")

if __name__ == "__main__":
    main()