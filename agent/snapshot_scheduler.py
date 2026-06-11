"""Background daemon thread — fetches config every interval and takes snapshots."""
import logging
import random
import threading
import time
from typing import Optional

from supabase import Client

import snapshot

logger = logging.getLogger(__name__)

_DEFAULT_MIN = 5   # minutes
_DEFAULT_MAX = 15  # minutes


def _fetch_config(supabase: Client, device_id: str) -> dict:
    """
    Returns merged config dict with keys:
      enabled: bool
      share_path: str | None
      min_interval: int (minutes)
      max_interval: int (minutes)
      display_name: str | None
      hostname: str | None
    Directory-level snapshot_enabled=false overrides device-level true.
    """
    try:
        res = supabase.table("devices").select(
            "snapshot_enabled, display_name, hostname, "
            "directories(snapshot_enabled, snapshot_share_path, snapshot_min_interval, snapshot_max_interval)"
        ).eq("id", device_id).single().execute()
        row = res.data or {}
        dir_cfg = row.get("directories") or {}

        dir_enabled = dir_cfg.get("snapshot_enabled") or False
        dev_enabled = row.get("snapshot_enabled")  # True | False | None

        if not dir_enabled:
            enabled = False
        elif dev_enabled is None:
            enabled = dir_enabled
        else:
            enabled = bool(dev_enabled)

        return {
            "enabled": enabled,
            "share_path": dir_cfg.get("snapshot_share_path"),
            "min_interval": dir_cfg.get("snapshot_min_interval") or _DEFAULT_MIN,
            "max_interval": dir_cfg.get("snapshot_max_interval") or _DEFAULT_MAX,
            "display_name": row.get("display_name"),
            "hostname": row.get("hostname"),
        }
    except Exception as e:
        logger.warning("snapshot_scheduler: config fetch failed: %s", e)
        return {
            "enabled": False,
            "share_path": None,
            "min_interval": _DEFAULT_MIN,
            "max_interval": _DEFAULT_MAX,
            "display_name": None,
            "hostname": None,
        }


def _scheduler_loop(supabase: Client, device_id: str) -> None:
    logger.info("Snapshot scheduler started for device %s", device_id)
    while True:
        cfg = _fetch_config(supabase, device_id)
        min_s = max(1, cfg["min_interval"]) * 60
        max_s = max(min_s, cfg["max_interval"] * 60)
        sleep_s = random.uniform(min_s, max_s)

        if cfg["enabled"] and cfg["share_path"]:
            try:
                written = snapshot.take(
                    share_path=cfg["share_path"],
                    display_name=cfg["display_name"],
                    hostname=cfg["hostname"],
                )
                if written:
                    logger.info("Snapshot: wrote %d file(s)", len(written))
            except Exception as e:
                logger.warning("Snapshot failed unexpectedly: %s", e)
        else:
            logger.debug("Snapshot disabled or no share path — skipping")

        time.sleep(sleep_s)


def start(supabase: Client, device_id: str) -> None:
    """Start the snapshot scheduler as a background daemon thread."""
    t = threading.Thread(
        target=_scheduler_loop,
        args=(supabase, device_id),
        daemon=True,
        name="snapshot-scheduler",
    )
    t.start()
    logger.info("Snapshot scheduler thread started")
