"""System tray icon with SOS button. Runs in its own thread.

On macOS LaunchDaemon (no GUI session), tray is silently skipped.
On macOS with GUI session (user login), tray runs via pystray AppKit backend.
"""
import logging
import os
import threading
from typing import Optional

from supabase import Client

from platform_utils import IS_MACOS

logger = logging.getLogger(__name__)


def _has_gui_session() -> bool:
    """Return True if running inside a GUI session (not a headless daemon)."""
    if IS_MACOS:
        # LaunchDaemons run as root with no GUI session.
        # Most reliable check: running as root almost always means daemon context.
        if os.getuid() == 0:
            return False
        # Secondary check: TERM_PROGRAM or DISPLAY set by a real user session.
        if os.environ.get("TERM_PROGRAM") or os.environ.get("DISPLAY"):
            return True
        return False
    # Windows: always has a desktop session when NSSM runs it interactively.
    return True


try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    logger.warning("pystray/Pillow not available — tray icon disabled")


def _create_icon_image() -> "Image.Image":
    img = Image.new("RGB", (64, 64), color=(30, 30, 30))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 56, 56], fill=(220, 50, 50))
    return img


def _send_sos_alert(supabase: Client, device_id: str) -> None:
    try:
        supabase.table("alerts_log").insert({
            "device_id": device_id,
            "severity": "critical",
            "message": "SOS: User requested help via system tray",
            "is_resolved": False,
        }).execute()
        logger.info("SOS alert sent for device %s", device_id)
    except Exception as e:
        logger.error("Failed to send SOS alert: %s", e)


def start_tray(supabase: Client, device_id: str) -> Optional[threading.Thread]:
    if not TRAY_AVAILABLE:
        return None
    if not _has_gui_session():
        logger.info("No GUI session detected — tray icon skipped")
        return None

    def on_sos(icon, item):
        _send_sos_alert(supabase, device_id)

    def on_quit(icon, item):
        icon.stop()

    icon = pystray.Icon(
        "RMM Agent",
        _create_icon_image(),
        "RMM Agent",
        menu=pystray.Menu(
            pystray.MenuItem("ขอความช่วยเหลือ (SOS)", on_sos),
            pystray.MenuItem("ออก", on_quit),
        ),
    )

    t = threading.Thread(target=icon.run, daemon=True)
    t.start()
    logger.info("Tray icon started")
    return t
