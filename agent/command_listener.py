"""Supabase Realtime listener — requires async client."""
import asyncio
import logging
import threading

from websockets.connection import State

from executor import execute_command

logger = logging.getLogger(__name__)

_HEALTH_CHECK_INTERVAL = 30


async def start_realtime_listener(supabase_async, supabase_sync, device_id: str) -> None:
    def on_command(payload: dict) -> None:
        data = payload.get("data", {})
        row = data.get("record") or payload.get("record") or payload.get("new", {})
        if not row or row.get("status") != "pending":
            return
        logger.info("Received command: %s (id=%s)", row.get("command_type"), row.get("id"))
        # executor uses sync supabase calls — run in thread
        t = threading.Thread(
            target=execute_command,
            args=(supabase_sync, device_id, row),
            daemon=True,
        )
        t.start()

    channel = supabase_async.channel(f"commands_{device_id}")
    channel.on_postgres_changes(
        event="INSERT",
        schema="public",
        table="commands_queue",
        filter=f"device_id=eq.{device_id}",
        callback=on_command,
    )
    try:
        await channel.subscribe()
    except Exception as e:
        raise ConnectionError(f"Realtime subscription failed: {e}") from e
    logger.info("Realtime listener subscribed for device %s", device_id)

    while True:
        await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
        ws = supabase_async.realtime._ws_connection
        if ws is None or ws.state != State.OPEN:
            logger.warning("Realtime websocket disconnected — reconnecting")
            await supabase_async.realtime._reconnect()
            logger.info("Realtime reconnected for device %s", device_id)
