"""Auto-update: compare version against agent_versions table, download and replace if newer."""
import logging
import os
import subprocess
import sys
import tempfile
from typing import Optional

import requests
from packaging.version import Version
from supabase import Client

from config import AGENT_VERSION

logger = logging.getLogger(__name__)


def check_and_update(supabase: Client) -> None:
    """
    Fetch latest version from Supabase. If newer, download exe to temp,
    replace current exe, then restart the service via NSSM.
    """
    try:
        res = (
            supabase.table("agent_versions")
            .select("version_number, download_url")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not res.data:
            return

        latest = res.data[0]
        latest_version = latest["version_number"]
        download_url = latest["download_url"]

        if Version(latest_version) <= Version(AGENT_VERSION):
            logger.debug("Agent is up to date (%s)", AGENT_VERSION)
            return

        logger.info("New version available: %s → %s", AGENT_VERSION, latest_version)
        _download_and_replace(download_url)

    except Exception as e:
        logger.warning("Auto-update check failed: %s", e)


def _download_and_replace(download_url: str) -> None:
    try:
        current_exe = sys.executable
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".exe")
        os.close(tmp_fd)

        response = requests.get(download_url, stream=True, timeout=120)
        response.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Replace current exe then restart service
        # bat script does the replace-after-exit trick
        bat = f"""
@echo off
ping 127.0.0.1 -n 3 > nul
move /Y "{tmp_path}" "{current_exe}"
nssm restart RMMAgent
"""
        bat_path = os.path.join(tempfile.gettempdir(), "rmm_update.bat")
        with open(bat_path, "w") as f:
            f.write(bat)

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            startupinfo=si,
            creationflags=subprocess.DETACHED_PROCESS,
        )
        logger.info("Update initiated — service will restart")
        sys.exit(0)

    except Exception as e:
        logger.error("_download_and_replace failed: %s", e)
