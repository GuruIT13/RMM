"""Auto-update: compare version against agent_versions table, download and replace if newer."""
import hashlib
import logging
import os
import stat
import subprocess
import sys
import tempfile

import requests
from packaging.version import Version
from supabase import Client

from config import AGENT_VERSION
from platform_utils import IS_WINDOWS, IS_MACOS

logger = logging.getLogger(__name__)


def _verify_checksum(file_path: str, expected_sha256: str) -> bool:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    actual = sha256.hexdigest().lower()
    expected = expected_sha256.lower()
    if actual != expected:
        logger.error("Checksum mismatch: expected %s got %s", expected, actual)
        return False
    return True


def check_and_update(supabase: Client) -> None:
    """Fetch latest version from Supabase. If newer, download and replace, then restart."""
    try:
        res = (
            supabase.table("agent_versions")
            .select("version_number, download_url, checksum_sha256")
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
        _download_and_replace(download_url, latest)

    except Exception as e:
        logger.warning("Auto-update check failed: %s", e)


def _download_and_replace(download_url: str, version_row: dict) -> None:
    try:
        current_exe = sys.executable
        suffix = ".exe" if IS_WINDOWS else ""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(tmp_fd)

        response = requests.get(download_url, stream=True, timeout=120)
        response.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        checksum = version_row.get("checksum_sha256")
        if checksum and not _verify_checksum(tmp_path, checksum):
            logger.error("Update aborted: checksum verification failed")
            os.remove(tmp_path)
            return

        if IS_WINDOWS:
            _restart_windows(tmp_path, current_exe)
        else:
            _restart_macos(tmp_path, current_exe)

    except Exception as e:
        logger.error("_download_and_replace failed: %s", e)


def _restart_windows(tmp_path: str, current_exe: str) -> None:
    bat = (
        "@echo off\r\n"
        "ping 127.0.0.1 -n 3 > nul\r\n"
        f'move /Y "{tmp_path}" "{current_exe}"\r\n'
        "nssm restart RMMAgent\r\n"
    )
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
    logger.info("Update initiated (Windows) — service will restart")
    sys.exit(0)


def _restart_macos(tmp_path: str, current_exe: str) -> None:
    # Make executable, replace current binary, restart via launchctl
    os.chmod(tmp_path, os.stat(tmp_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    sh = (
        "#!/bin/sh\n"
        "sleep 3\n"
        f'mv -f "{tmp_path}" "{current_exe}"\n'
        "launchctl kickstart -k system/com.rmm.agent\n"
    )
    sh_path = os.path.join(tempfile.gettempdir(), "rmm_update.sh")
    with open(sh_path, "w") as f:
        f.write(sh)
    os.chmod(sh_path, 0o755)
    subprocess.Popen(
        ["bash", sh_path],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Update initiated (macOS) — service will restart")
    sys.exit(0)
