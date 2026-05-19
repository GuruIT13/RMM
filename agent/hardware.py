"""Collect hardware metrics. All functions return None/default on failure — never raise."""
import logging
import platform
import subprocess
from typing import Optional

import psutil

logger = logging.getLogger(__name__)


def get_serial_number() -> str:
    """Use WMIC to get motherboard serial. Falls back to hostname if unavailable."""
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(
            ["wmic", "bios", "get", "SerialNumber", "/value"],
            capture_output=True, text=True, timeout=10, startupinfo=si
        )
        for line in result.stdout.splitlines():
            if line.startswith("SerialNumber="):
                serial = line.split("=", 1)[1].strip()
                if serial:
                    return serial
    except Exception as e:
        logger.warning("get_serial_number failed: %s", e)
    return platform.node()  # hostname as fallback


def get_cpu_name() -> Optional[str]:
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(
            ["wmic", "cpu", "get", "Name", "/value"],
            capture_output=True, text=True, timeout=10, startupinfo=si
        )
        for line in result.stdout.splitlines():
            if line.startswith("Name="):
                return line.split("=", 1)[1].strip() or None
    except Exception as e:
        logger.warning("get_cpu_name failed: %s", e)
    return None


def get_cpu_usage() -> float:
    try:
        return psutil.cpu_percent(interval=1)
    except Exception as e:
        logger.warning("get_cpu_usage failed: %s", e)
        return 0.0


def get_cpu_temp() -> Optional[float]:
    """Windows doesn't expose CPU temp via psutil — requires WMI or vendor tool."""
    try:
        import wmi  # type: ignore
        w = wmi.WMI(namespace="root/wmi")
        sensors = w.MSAcpi_ThermalZoneTemperature()
        if sensors:
            # Convert from tenths of Kelvin to Celsius
            return (sensors[0].CurrentTemperature / 10.0) - 273.15
    except Exception as e:
        logger.debug("get_cpu_temp failed (expected if no WMI sensor): %s", e)
    return None


def get_ram_total() -> int:
    try:
        return psutil.virtual_memory().total
    except Exception as e:
        logger.warning("get_ram_total failed: %s", e)
        return 0


def get_ram_usage() -> float:
    try:
        return psutil.virtual_memory().percent
    except Exception as e:
        logger.warning("get_ram_usage failed: %s", e)
        return 0.0


def get_storage_info() -> tuple[int, int]:
    """Returns (total_bytes, free_bytes) for the C: drive."""
    try:
        usage = psutil.disk_usage("C:\\")
        return usage.total, usage.free
    except Exception as e:
        logger.warning("get_storage_info failed: %s", e)
        return 0, 0


def get_os_info() -> str:
    try:
        return f"{platform.system()} {platform.release()} {platform.version()}"
    except Exception:
        return "Unknown"


def get_firewall_status() -> Optional[bool]:
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(
            ["netsh", "advfirewall", "show", "allprofiles", "state"],
            capture_output=True, text=True, timeout=10, startupinfo=si
        )
        # If any profile is ON, return True
        return "ON" in result.stdout.upper()
    except Exception as e:
        logger.warning("get_firewall_status failed: %s", e)
        return None


def get_antivirus_status() -> Optional[str]:
    try:
        import wmi  # type: ignore
        w = wmi.WMI(namespace="root/SecurityCenter2")
        products = w.AntiVirusProduct()
        if products:
            return products[0].displayName
    except Exception as e:
        logger.debug("get_antivirus_status failed: %s", e)
    return None


def collect_all() -> dict:
    storage_total, storage_free = get_storage_info()
    return {
        "hostname": platform.node(),
        "os_info": get_os_info(),
        "cpu_name": get_cpu_name(),
        "cpu_usage": get_cpu_usage(),
        "cpu_temp": get_cpu_temp(),
        "ram_total": get_ram_total(),
        "ram_usage": get_ram_usage(),
        "storage_total": storage_total,
        "storage_free": storage_free,
        "firewall_status": get_firewall_status(),
        "antivirus_status": get_antivirus_status(),
    }
