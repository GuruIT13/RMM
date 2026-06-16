"""
RMM Agent — main entry point.
Runs as a Windows Service via NSSM, or directly with: python main.py
"""
import asyncio
import logging
import os
import signal
import ssl
import sys
import time
from logging.handlers import RotatingFileHandler

# macOS Homebrew Python lacks system CA bundle — point to certifi if available
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    ssl._create_default_https_context = ssl.create_default_context
except ImportError:
    pass

from supabase import create_client                        # sync — for registration/heartbeat
from supabase import acreate_client                       # async — for Realtime

import config
from registration import get_or_register_device, send_heartbeat, mark_offline
from command_listener import start_realtime_listener
from updater import check_and_update
from tray import start_tray
import snapshot_scheduler

logger = logging.getLogger(__name__)

_MAX_AUTH_FAILURES = 3


def setup_logging() -> None:
    handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[handler],
    )


async def heartbeat_loop(supabase_sync, device_id: str) -> None:
    logger.info("Heartbeat loop started (interval=%ss)", config.HEARTBEAT_INTERVAL)
    while True:
        try:
            send_heartbeat(supabase_sync, device_id)
        except Exception as e:
            logger.warning("Heartbeat failed: %s", e)
        await asyncio.sleep(config.HEARTBEAT_INTERVAL)


async def realtime_loop(supabase_sync, device_id: str) -> None:
    """Realtime listener with auto-reconnect on failure. Stops after repeated auth failures."""
    retry_delay = 5
    auth_failures = 0
    while True:
        try:
            supabase_async = await acreate_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
            logger.info("Realtime client created, connecting…")
            await start_realtime_listener(supabase_async, supabase_sync, device_id)
        except PermissionError as e:
            auth_failures += 1
            logger.critical("Realtime auth failure %d/%d: %s", auth_failures, _MAX_AUTH_FAILURES, e)
            if auth_failures >= _MAX_AUTH_FAILURES:
                logger.critical("Too many auth failures — Realtime listener shutting down. Check SUPABASE_ANON_KEY.")
                return  # stop retrying; heartbeat loop continues
            await asyncio.sleep(retry_delay)
        except Exception as e:
            auth_failures = 0  # reset on non-auth error
            logger.error("Realtime listener crashed: %s — retrying in %ss", e, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        else:
            auth_failures = 0
            retry_delay = 5


async def main_async() -> None:
    setup_logging()
    logger.info("RMM Agent v%s starting", config.AGENT_VERSION)

    supabase_sync = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

    device_id = get_or_register_device(supabase_sync)
    if not device_id:
        logger.critical("Cannot register device — exiting")
        sys.exit(1)

    check_and_update(supabase_sync)
    start_tray(supabase_sync, device_id)
    snapshot_scheduler.start(supabase_sync, device_id)

    loop = asyncio.get_running_loop()

    def _stop():
        mark_offline(supabase_sync, device_id)
        logger.info("Agent stopped")
        loop.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    await asyncio.gather(
        heartbeat_loop(supabase_sync, device_id),
        realtime_loop(supabase_sync, device_id),
    )


if __name__ == "__main__":
    # Outer retry loop — restart entire agent if asyncio.run itself crashes
    while True:
        try:
            asyncio.run(main_async())
        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.getLogger(__name__).critical("Agent crashed: %s — restarting in 10s", e)
            time.sleep(10)
