import logging
import asyncio
from flask import Flask, request, current_app

logger = logging.getLogger(__name__)

def create_webhook_app(bot, payment_processor):
    flask_app = Flask(__name__)

    @flask_app.route('/yookassa-webhook', methods=['POST'])
    def yookassa_webhook_handler():
        try:
            event_json = request.json
            if event_json.get("event") == "payment.succeeded":
                metadata = event_json.get("object", {}).get("metadata", {})
                if metadata:
                    loop = current_app.config['EVENT_LOOP']
                    asyncio.run_coroutine_threadsafe(payment_processor(bot, metadata), loop)
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error in yookassa webhook handler: {e}")
            return 'Error', 500

    @flask_app.route('/crypto-webhook', methods=['POST'])
    def crypto_webhook_handler():
        try:
            data = request.json
            logger.info(f"Crypto webhook received: {data}")

            if data.get("status") == "paid":
                metadata = data.get("metadata", {})
                if metadata:
                    loop = current_app.config['EVENT_LOOP']
                    asyncio.run_coroutine_threadsafe(payment_processor(bot, metadata), loop)
            
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error in crypto webhook handler: {e}")
            return 'Error', 500

    return flask_app