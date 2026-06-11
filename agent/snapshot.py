"""Screenshot capture — writes PNG files to a UNC network share."""
import logging
import re
import socket
from datetime import datetime
from pathlib import Path
from typing import Optional

import mss
import mss.tools

logger = logging.getLogger(__name__)

_FORBIDDEN = re.compile(r'[/\\:*?"<>|]')


def _safe_name(name: str) -> str:
    return _FORBIDDEN.sub("_", name).strip() or "device"


def take(
    share_path: str,
    display_name: Optional[str],
    hostname: Optional[str],
) -> list[str]:
    """
    Capture all monitors and write PNGs to share_path.
    Returns list of filenames written (basenames only).
    Falls back to hostname if display_name is None/empty.
    Returns [] on any failure — never raises.
    """
    dest = Path(share_path)
    if not dest.is_absolute():
        logger.warning("Snapshot share path is not absolute: %s", share_path)
        return []

    prefix = _safe_name(display_name or hostname or socket.gethostname())
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    written: list[str] = []
    try:
        with mss.mss() as sct:
            for i, monitor in enumerate(sct.monitors[1:], start=1):
                filename = f"{prefix}_{timestamp}_monitor{i}.png"
                filepath = dest / filename
                try:
                    img = sct.grab(monitor)
                    mss.tools.to_png(img.rgb, img.size, output=str(filepath))
                    written.append(filename)
                    logger.info("Snapshot saved: %s", filepath)
                except Exception as e:
                    logger.warning("Snapshot monitor %d failed: %s", i, e)
    except Exception as e:
        logger.warning("Snapshot share inaccessible (%s): %s", share_path, e)

    return written
