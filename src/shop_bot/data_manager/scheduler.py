import asyncio
import logging
from datetime import datetime

from shop_bot.data_manager import database
from shop_bot.modules import xui_api

CHECK_INTERVAL_SECONDS = 300 
logger = logging.getLogger(__name__)

async def periodic_subscription_check():
    logger.info("Scheduler has been started. Initial check will be in a moment.")
    await asyncio.sleep(10)

    while True:
        logger.info("Scheduler: Starting periodic subscription check cycle...")
        total_affected_records = 0

        all_hosts = database.get_all_hosts()
        if not all_hosts:
            logger.info("Scheduler: No hosts configured in the database. Skipping check.")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            continue

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