"""Device self-registration and heartbeat updates."""
import logging
import platform
from typing import Optional

from supabase import Client

from hardware import collect_all, get_serial_number
from config import AGENT_VERSION

logger = logging.getLogger(__name__)


def get_or_register_device(supabase: Client) -> Optional[str]:
    """
    Returns device_id (UUID string) after ensuring this machine is registered.
    Inserts as Unassigned (directory_id=NULL, is_approved=FALSE) on first run.
    """
    serial = get_serial_number()
    hostname = platform.node()

    try:
        # Check if already registered
        res = supabase.table("devices").select("id").eq("serial_number", serial).execute()
        if res.data:
            device_id = res.data[0]["id"]
            logger.info("Device already registered: %s", device_id)
            return device_id

        # First run — insert as Unassigned
        metrics = collect_all()
        insert_data = {
            "serial_number": serial,
            "hostname": hostname,
            "status": "online",
            "is_approved": False,
            **metrics,
        }
        res = supabase.table("devices").insert(insert_data).execute()
        device_id = res.data[0]["id"]
        logger.info("Registered new device: %s (Unassigned)", device_id)
        return device_id

    except Exception as e:
        logger.error("get_or_register_device failed: %s", e)
        return None


def send_heartbeat(supabase: Client, device_id: str) -> None:
    """Push latest metrics and mark device online."""
    try:
        metrics = collect_all()
        update_data = {
            "status": "online",
            "last_seen": "now()",
            **metrics,
        }
        supabase.table("devices").update(update_data).eq("id", device_id).execute()
        logger.debug("Heartbeat sent for %s", device_id)
    except Exception as e:
        logger.warning("send_heartbeat failed: %s", e)


def mark_offline(supabase: Client, device_id: str) -> None:
    try:
        supabase.table("devices").update({"status": "offline"}).eq("id", device_id).execute()
        logger.info("Device marked offline: %s", device_id)
    except Exception as e:
        logger.warning("mark_offline failed: %s", e)
