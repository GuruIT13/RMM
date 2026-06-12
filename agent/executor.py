"""Execute commands received from commands_queue. All runs are hidden (no CMD window)."""
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional

from supabase import Client
import re as _re

from config import COMMAND_TIMEOUT
import snapshot as _snapshot
from platform_utils import IS_WINDOWS, IS_MACOS

logger = logging.getLogger(__name__)

_PROCESS_NAME_WIN_RE = _re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,253}\.exe$', _re.IGNORECASE)
_PROCESS_NAME_MAC_RE = _re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._\- ]{0,253}$')
_CUSTOM_CMD_MAX_LEN = 2000

_ANYDESK_SEARCH_PATHS = [
    r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe",
    r"C:\Program Files\AnyDesk\AnyDesk.exe",
    r"C:\ProgramData\AnyDesk\AnyDesk.exe",
]

_ANYDESK_MACOS_PATH = "/Applications/AnyDesk.app/Contents/MacOS/AnyDesk"


def _find_anydesk() -> Optional[str]:
    if IS_MACOS:
        if os.path.isfile(_ANYDESK_MACOS_PATH):
            return _ANYDESK_MACOS_PATH
        return None
    # Windows
    import winreg
    for p in _ANYDESK_SEARCH_PATHS:
        if os.path.isfile(p):
            return p
    try:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\AnyDesk", r"SOFTWARE\WOW6432Node\AnyDesk"):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        val, _ = winreg.QueryValueEx(k, "exe")
                        if os.path.isfile(val):
                            return val
                except OSError:
                    pass
    except Exception:
        pass
    return None


def _hidden_startupinfo() -> subprocess.STARTUPINFO:
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si


def _run(args: list[str], timeout: int = COMMAND_TIMEOUT, shell: bool = False) -> str:
    try:
        kwargs: dict = dict(capture_output=True, text=True, timeout=timeout, shell=shell)
        if IS_WINDOWS:
            kwargs["startupinfo"] = _hidden_startupinfo()
        result = subprocess.run(args, **kwargs)
        return (result.stdout + result.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {timeout}s"
    except Exception as e:
        return f"ERROR: {e}"


def _ps(script: str, timeout: int = COMMAND_TIMEOUT) -> str:
    return _run(["powershell.exe", "-NonInteractive", "-Command", script], timeout=timeout)


# ── existing handlers ────────────────────────────────────────────────────────

def handle_get_anydesk_id(supabase: Client, device_id: str) -> str:
    anydesk_exe = _find_anydesk()
    if not anydesk_exe:
        return "ERROR: AnyDesk not installed"
    output = _run([anydesk_exe, "--get-id"], timeout=15)
    anydesk_id = output.strip()
    if anydesk_id.isdigit():
        try:
            supabase.table("devices").update({"anydesk_id": anydesk_id}).eq("id", device_id).execute()
        except Exception as e:
            logger.warning("Failed to save anydesk_id: %s", e)
    return anydesk_id


def handle_disk_cleanup() -> str:
    if IS_WINDOWS:
        return _run(["cleanmgr.exe", "/sagerun:1"])
    return _run(["sudo", "periodic", "daily", "weekly", "monthly"], timeout=300)


def handle_windows_update() -> str:
    if IS_WINDOWS:
        script = (
            "$session = New-Object -ComObject Microsoft.Update.Session; "
            "$searcher = $session.CreateUpdateSearcher(); "
            "$result = $searcher.Search('IsInstalled=0 and Type=''Software'''); "
            "if ($result.Updates.Count -eq 0) { 'No updates available'; return }; "
            "$downloader = $session.CreateUpdateDownloader(); "
            "$downloader.Updates = $result.Updates; "
            "$downloader.Download() | Out-Null; "
            "$installer = $session.CreateUpdateInstaller(); "
            "$installer.Updates = $result.Updates; "
            "$installResult = $installer.Install(); "
            "\"Installed $($result.Updates.Count) update(s). ResultCode=$($installResult.ResultCode) RebootRequired=$($installResult.RebootRequired)\""
        )
        return _ps(script, timeout=1800)
    return _run(["softwareupdate", "-ia"], timeout=1800)


def handle_kill_process(payload: dict) -> str:
    process_name = payload.get("process_name", "").strip()
    if IS_WINDOWS:
        if not process_name or not _PROCESS_NAME_WIN_RE.match(process_name):
            return "ERROR: Invalid process_name — must be a valid .exe filename (e.g. notepad.exe)"
        return _run(["taskkill", "/F", "/IM", process_name])
    else:
        # strip .exe suffix if user sent a Windows-style name
        name = _re.sub(r'\.exe$', '', process_name, flags=_re.IGNORECASE)
        if not name or not _PROCESS_NAME_MAC_RE.match(name):
            return "ERROR: Invalid process_name"
        return _run(["pkill", "-9", name])


def handle_reboot() -> str:
    if IS_WINDOWS:
        return _run(["shutdown", "/r", "/t", "0", "/f"])
    return _run(["sudo", "shutdown", "-r", "now"])


def handle_shutdown() -> str:
    if IS_WINDOWS:
        return _run(["shutdown", "/s", "/t", "0", "/f"])
    return _run(["sudo", "shutdown", "-h", "now"])


def handle_custom_cmd(payload: dict) -> str:
    command = payload.get("command", "").strip()
    if not command:
        return "ERROR: Empty command"
    if len(command) > _CUSTOM_CMD_MAX_LEN:
        return f"ERROR: Command exceeds {_CUSTOM_CMD_MAX_LEN} character limit"
    if IS_WINDOWS:
        return _run(["cmd.exe", "/c", command], timeout=COMMAND_TIMEOUT)
    return _run(["bash", "-c", command], timeout=COMMAND_TIMEOUT)


# ── new handlers ─────────────────────────────────────────────────────────────

def handle_get_system_info() -> str:
    if IS_WINDOWS:
        script = (
            "$os = Get-CimInstance Win32_OperatingSystem; "
            "$uptime = (Get-Date) - $os.LastBootUpTime; "
            "\"OS: $($os.Caption) $($os.Version)\n"
            "Build: $($os.BuildNumber)\n"
            "Last Boot: $($os.LastBootUpTime)\n"
            "Uptime: $([int]$uptime.TotalHours)h $($uptime.Minutes)m\n"
            "Install Date: $($os.InstallDate)\""
        )
        return _ps(script, timeout=30)
    vers = _run(["sw_vers"], timeout=10)
    uptime = _run(["uptime"], timeout=10)
    return f"{vers}\n{uptime}"


def handle_list_processes() -> str:
    script = (
        "Get-Process | Sort-Object CPU -Descending | Select-Object -First 50 | "
        "Select-Object Name, Id, "
        "@{N='CPU';E={[math]::Round($_.CPU,1)}}, "
        "@{N='RAM_MB';E={[math]::Round($_.WorkingSet64/1MB,1)}} | "
        "ConvertTo-Json -Compress"
    )
    return _ps(script, timeout=30)


def handle_list_installed_software() -> str:
    if IS_WINDOWS:
        script = (
            "$paths = 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
            "'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'; "
            "Get-ItemProperty $paths -ErrorAction SilentlyContinue | "
            "Where-Object DisplayName | "
            "Sort-Object DisplayName | "
            "Select-Object DisplayName, DisplayVersion, Publisher, InstallDate, EstimatedSize | "
            "ConvertTo-Json -Compress"
        )
        return _ps(script, timeout=30)
    return _run(["system_profiler", "SPApplicationsDataType", "-json"], timeout=60)


def handle_get_event_logs() -> str:
    if IS_WINDOWS:
        script = (
            "$since = (Get-Date).AddHours(-24); "
            "Get-WinEvent -FilterHashtable @{LogName='System','Application'; Level=1,2; StartTime=$since} "
            "-MaxEvents 50 -ErrorAction SilentlyContinue | "
            "Select-Object TimeCreated, LevelDisplayName, ProviderName, Message | "
            "Format-List | Out-String -Width 120"
        )
        return _ps(script, timeout=30)
    return _run([
        "log", "show", "--last", "24h",
        "--predicate", "eventType == faultEvent",
        "--style", "compact"
    ], timeout=60)


def handle_run_sfc() -> str:
    if IS_WINDOWS:
        return _run(["sfc", "/scannow"], timeout=600)
    return _run(["diskutil", "verifyVolume", "/"], timeout=120)


def handle_flush_dns() -> str:
    if IS_WINDOWS:
        return _run(["ipconfig", "/flushdns"], timeout=15)
    out1 = _run(["dscacheutil", "-flushcache"], timeout=15)
    out2 = _run(["sudo", "killall", "-HUP", "mDNSResponder"], timeout=15)
    return f"{out1}\n{out2}".strip()


def handle_clear_temp() -> str:
    if IS_WINDOWS:
        script = (
            "$dirs = @($env:TEMP, 'C:\\Windows\\Temp'); "
            "$total = 0; "
            "foreach ($d in $dirs) { "
            "  $files = Get-ChildItem $d -Recurse -Force -ErrorAction SilentlyContinue; "
            "  $size = ($files | Measure-Object Length -Sum).Sum; "
            "  Remove-Item \"$d\\*\" -Recurse -Force -ErrorAction SilentlyContinue; "
            "  $total += $size "
            "}; "
            "\"Cleared approx $([math]::Round($total/1MB,1)) MB\""
        )
        return _ps(script, timeout=60)
    import shutil, os
    cleared = []
    errors = []
    for target in ["/tmp", os.path.expanduser("~/Library/Caches")]:
        try:
            for item in os.listdir(target):
                item_path = os.path.join(target, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                    else:
                        os.remove(item_path)
                except Exception:
                    pass
            cleared.append(target)
        except Exception as e:
            errors.append(f"{target}: {e}")
    result = f"Cleared: {', '.join(cleared)}"
    if errors:
        result += f"\nErrors: {'; '.join(errors)}"
    return result


def handle_get_network_info() -> str:
    if IS_WINDOWS:
        script = (
            "Get-NetIPConfiguration | ForEach-Object { "
            "  $a = $_.IPv4Address; "
            "  \"Interface: $($_.InterfaceAlias)\n"
            "  IP: $($a.IPAddress)\n"
            "  Gateway: $($_.IPv4DefaultGateway.NextHop)\n"
            "  DNS: $($_.DNSServer.ServerAddresses -join ', ')\n\" "
            "}; "
            "Get-NetAdapter | Where-Object Status -eq Up | "
            "Select-Object Name, MacAddress | Format-Table | Out-String"
        )
        return _ps(script, timeout=15)
    return _run(["ifconfig"], timeout=15)


def handle_ping_test(payload: dict) -> str:
    host = payload.get("host", "").strip()
    if not host:
        return "ERROR: Missing host in payload"
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_")
    if not all(c in allowed for c in host):
        return "ERROR: Invalid host"
    if IS_WINDOWS:
        return _run(["ping", "-n", "4", host], timeout=30)
    return _run(["ping", "-c", "4", host], timeout=30)


def handle_lock_screen() -> str:
    if IS_WINDOWS:
        _ps("rundll32.exe user32.dll,LockWorkStation", timeout=5)
    else:
        _run(["pmset", "displaysleepnow"], timeout=5)
    return "Screen locked"


def handle_enable_rdp() -> str:
    if IS_WINDOWS:
        script = (
            "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' "
            "-Name fDenyTSConnections -Value 0; "
            "Enable-NetFirewallRule -DisplayGroup 'Remote Desktop'; "
            "'RDP enabled'"
        )
        return _ps(script, timeout=15)
    return _run(["sudo", "systemsetup", "-setremotelogin", "on"], timeout=15)


def handle_disable_rdp() -> str:
    if IS_WINDOWS:
        script = (
            "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' "
            "-Name fDenyTSConnections -Value 1; "
            "Disable-NetFirewallRule -DisplayGroup 'Remote Desktop'; "
            "'RDP disabled'"
        )
        return _ps(script, timeout=15)
    return _run(["sudo", "systemsetup", "-setremotelogin", "off"], timeout=15)


def handle_get_bitlocker_status() -> str:
    if IS_WINDOWS:
        script = (
            "Get-BitLockerVolume -ErrorAction SilentlyContinue | "
            "Select-Object MountPoint, VolumeStatus, EncryptionPercentage, ProtectionStatus | "
            "Format-Table -AutoSize | Out-String"
        )
        return _ps(script, timeout=15)
    return _run(["fdesetup", "status"], timeout=15)


def handle_enable_bitlocker(payload: dict) -> str:
    if IS_WINDOWS:
        drive = payload.get("drive", "C:").strip().rstrip("\\")
        if len(drive) != 2 or drive[1] != ":" or not drive[0].isalpha():
            return "ERROR: Invalid drive letter"
        script = (
            f"Enable-BitLocker -MountPoint '{drive}' -EncryptionMethod XtsAes256 "
            f"-UsedSpaceOnly -TpmProtector -ErrorAction Stop; "
            f"'BitLocker enabling on {drive} — may take time'"
        )
        return _ps(script, timeout=30)
    return _run(["sudo", "fdesetup", "enable"], timeout=30)


def handle_disable_bitlocker(payload: dict) -> str:
    if IS_WINDOWS:
        drive = payload.get("drive", "C:").strip().rstrip("\\")
        if len(drive) != 2 or drive[1] != ":" or not drive[0].isalpha():
            return "ERROR: Invalid drive letter"
        script = (
            f"Disable-BitLocker -MountPoint '{drive}' -ErrorAction Stop; "
            f"'BitLocker disabling on {drive} — decryption running in background'"
        )
        return _ps(script, timeout=30)
    return _run(["sudo", "fdesetup", "disable"], timeout=30)


def handle_get_hardware_devices() -> str:
    if IS_WINDOWS:
        script = (
            "Get-PnpDevice -PresentOnly | "
            "Sort-Object Class, FriendlyName | "
            "Select-Object Status, Class, FriendlyName, InstanceId | "
            "ConvertTo-Json -Compress"
        )
        return _ps(script, timeout=30)
    return _run(["system_profiler", "SPUSBDataType", "SPPCIDataType", "-json"], timeout=30)


def handle_uninstall_software(payload: dict) -> str:
    name = payload.get("name", "").strip()
    if not name:
        return "ERROR: Missing name in payload"
    if IS_WINDOWS:
        # Escape single quotes for PowerShell string context
        name = name.replace("'", "''")
        # lookup uninstall string from registry — never execute raw user input
        script = (
            f"$paths = 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
            f"'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'; "
            f"$app = Get-ItemProperty $paths -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.DisplayName -eq '{name}' }} | Select-Object -First 1; "
            f"if (-not $app) {{ 'ERROR: App not found in registry'; return }}; "
            f"$us = $app.UninstallString; "
            f"if (-not $us) {{ 'ERROR: No UninstallString found'; return }}; "
            f"if ($us -match 'msiexec') {{"
            f"  $prod = $us -replace '.*\\{{(.+?)\\}}.*','{{$1}}'; "
            f"  Start-Process msiexec -ArgumentList \"/x $prod /qn /norestart\" -Wait; "
            f"  'Uninstall completed (MSI)' "
            f"}} else {{"
            f"  Start-Process cmd -ArgumentList \"/c $us /S /SILENT /quiet\" -Wait; "
            f"  'Uninstall completed' "
            f"}}"
        )
        return _ps(script, timeout=300)
    if "/" in name or "\\" in name or ".." in name:
        return "ERROR: Invalid app name"
    app_path = f"/Applications/{name}.app"
    if not os.path.isdir(app_path):
        return f"ERROR: {app_path} not found"
    return _run(["sudo", "rm", "-rf", app_path], timeout=60)


def handle_run_defender_scan() -> str:
    if IS_MACOS:
        return "Not supported on macOS — XProtect runs automatically"
    script = (
        "try { Start-MpScan -ScanType QuickScan -ErrorAction Stop } "
        "catch { if ($_.Exception.Message -match 'already in progress') { 'Scan already in progress' } "
        "        else { throw } }; "
        "$s = Get-MpComputerStatus; "
        "\"Defender quick scan started`n"
        "AMRunning: $($s.AMRunningMode)`n"
        "LastQuickScan: $($s.QuickScanEndTime)`n"
        "LastFullScan: $($s.FullScanEndTime)\""
    )
    return _ps(script, timeout=300)


def handle_take_snapshot(supabase: Client, device_id: str) -> str:
    try:
        res = supabase.table("devices").select(
            "display_name, hostname, "
            "directories(snapshot_share_path)"
        ).eq("id", device_id).single().execute()
        row = res.data or {}
        share_path = (row.get("directories") or {}).get("snapshot_share_path")
        if not share_path:
            return "ERROR: No snapshot_share_path configured for this directory"
        written = _snapshot.take(
            share_path=share_path,
            display_name=row.get("display_name"),
            hostname=row.get("hostname"),
        )
        if not written:
            return "ERROR: No screenshots captured (share inaccessible or no monitors?)"
        return f"Captured {len(written)} file(s): {', '.join(written)}"
    except Exception as e:
        return f"ERROR: {e}"


# ── dispatch table ───────────────────────────────────────────────────────────

COMMAND_HANDLERS: dict = {
    "get_anydesk_id":           None,  # handled separately (needs supabase + device_id)
    "disk_cleanup":             (handle_disk_cleanup, []),
    "windows_update":           (handle_windows_update, []),
    "kill_process":             (handle_kill_process, ["payload"]),
    "reboot":                   (handle_reboot, []),
    "shutdown":                 (handle_shutdown, []),
    "custom_cmd":               (handle_custom_cmd, ["payload"]),
    "get_system_info":          (handle_get_system_info, []),
    "list_processes":           (handle_list_processes, []),
    "list_installed_software":  (handle_list_installed_software, []),
    "get_event_logs":           (handle_get_event_logs, []),
    "run_sfc":                  (handle_run_sfc, []),
    "flush_dns":                (handle_flush_dns, []),
    "clear_temp":               (handle_clear_temp, []),
    "get_network_info":         (handle_get_network_info, []),
    "ping_test":                (handle_ping_test, ["payload"]),
    "lock_screen":              (handle_lock_screen, []),
    "enable_rdp":               (handle_enable_rdp, []),
    "disable_rdp":              (handle_disable_rdp, []),
    "get_bitlocker_status":     (handle_get_bitlocker_status, []),
    "enable_bitlocker":         (handle_enable_bitlocker, ["payload"]),
    "disable_bitlocker":        (handle_disable_bitlocker, ["payload"]),
    "run_defender_scan":        (handle_run_defender_scan, []),
    "get_hardware_devices":     (handle_get_hardware_devices, []),
    "uninstall_software":       (handle_uninstall_software, ["payload"]),
    "take_snapshot":            None,  # handled separately (needs supabase + device_id)
}


def execute_command(supabase: Client, device_id: str, command_row: dict) -> None:
    cmd_id = command_row["id"]
    cmd_type = command_row.get("command_type", "")
    payload = command_row.get("payload") or {}

    logger.info("Executing command %s: %s", cmd_id, cmd_type)

    try:
        supabase.table("commands_queue").update({"status": "executing"}).eq("id", cmd_id).execute()
    except Exception as e:
        logger.warning("Failed to mark executing: %s", e)

    try:
        if cmd_type == "get_anydesk_id":
            output = handle_get_anydesk_id(supabase, device_id)
        elif cmd_type == "take_snapshot":
            output = handle_take_snapshot(supabase, device_id)
        elif cmd_type in COMMAND_HANDLERS and COMMAND_HANDLERS[cmd_type]:
            handler_fn, arg_spec = COMMAND_HANDLERS[cmd_type]
            output = handler_fn(payload) if "payload" in arg_spec else handler_fn()
        else:
            output = f"ERROR: Unknown command_type '{cmd_type}'"
        status = "completed"
    except Exception as e:
        output = f"ERROR: Unhandled exception: {e}"
        status = "failed"
        logger.error("Command %s failed: %s", cmd_id, e)

    try:
        supabase.table("commands_queue").update({
            "status": status,
            "output_result": output,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", cmd_id).execute()
    except Exception as e:
        logger.error("Failed to write command result: %s", e)
