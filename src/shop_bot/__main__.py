import logging
import threading
import asyncio
import signal

from shop_bot.webhook_server.app import create_webhook_app
from shop_bot.data_manager.scheduler import periodic_subscription_check, init_scheduler
from shop_bot.data_manager import database
from shop_bot.bot_controller import BotController

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"
    )
    logger = logging.getLogger(__name__)

    database.initialize_db()
    logger.info("Database initialization check complete.")

    bot_controller = BotController()
    flask_app = create_webhook_app(bot_controller)
    
    async def shutdown(sig: signal.Signals, loop: asyncio.AbstractEventLoop):
        logger.info(f"Received signal: {sig.name}. Shutting down...")
        if bot_controller.get_status()["is_running"]:
            bot_controller.stop()
            await asyncio.sleep(2)
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            [task.cancel() for task in tasks]
            await asyncio.gather(*tasks, return_exceptions=True)
        loop.stop()

    async def start_services():
        loop = asyncio.get_running_loop()
        bot_controller.set_loop(loop)
        flask_app.config['EVENT_LOOP'] = loop
        
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda sig=sig: asyncio.create_task(shutdown(sig, loop)))
        
        flask_thread = threading.Thread(
            target=lambda: flask_app.run(host='0.0.0.0', port=1488, use_reloader=False, debug=False),
            daemon=True
        )
        flask_thread.start()
        logger.info("Flask server started in a background thread on http://0.0.0.0:1488")
        
        max_attempts = 10
        for attempt in range(max_attempts):
            bot = bot_controller.get_bot_instance()
            if bot:
                init_scheduler(bot)
                logger.info("Scheduler initialized with bot instance")
                break
            logger.info(f"Waiting for bot initialization... (attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(1)
        else:
            logger.error("Failed to initialize scheduler: bot instance not available")
            
        logger.info("Application is running. Bot can be started from the web panel.")
        
        asyncio.create_task(periodic_subscription_check())

        await asyncio.Future()

    try:
        asyncio.run(start_services())
    finally:
        logger.info("Application is shutting down.")

if __name__ == "__main__":
    main()