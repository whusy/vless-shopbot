import asyncio
import logging
from datetime import datetime

from data_manager import database
import modules.xui_api as xui_api

CHECK_INTERVAL_SECONDS = 300
logger = logging.getLogger(__name__)

async def periodic_subscription_check():
    logger.info("Scheduler has been started.")
    while True:
        try:
            logger.info("Scheduler: Starting periodic subscription check...")
            
            api, _ = xui_api.login()
            if not api:
                logger.error("Scheduler: Could not log in to X-UI panel. Skipping.")
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
                continue

            vpn_users = database.get_all_vpn_users()
            if not vpn_users:
                logger.info("Scheduler: No users with VPN keys in DB to check.")
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
                continue
            
            logger.info(f"Scheduler: Found {len(vpn_users)} users with keys to check.")
            updated_count = 0

            for user_entry in vpn_users:
                user_id = user_entry['user_id']
                user_keys_in_db = database.get_user_keys(user_id)
                
                for key in user_keys_in_db:
                    key_email = key['key_email']
                    xui_client = xui_api.get_client_by_email(key_email, api)
                    
                    if xui_client:
                        server_expiry_ms = xui_client.expiry_time
                        local_expiry_dt = datetime.fromisoformat(key['expiry_date'])
                        local_expiry_ms = int(local_expiry_dt.timestamp() * 1000)

                        if abs(server_expiry_ms - local_expiry_ms) > 1000:
                            database.update_key_status_from_server(key_email, xui_client)
                            updated_count += 1
                            logger.info(f"Scheduler: Synced key {key_email} for user {user_id}.")
                    else:
                        logger.warning(f"Scheduler: Key {key_email} for user {user_id} not found on server. Deleting from local DB.")
                        database.update_key_status_from_server(key_email, None)
                        updated_count += 1
            
            logger.info(f"Scheduler: Check finished. Records affected: {updated_count}.")

        except Exception as e:
            logger.error(f"Scheduler: An unexpected error occurred: {e}", exc_info=True)
        
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)