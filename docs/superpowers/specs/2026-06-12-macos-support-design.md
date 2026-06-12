# macOS Support for RMM Agent — Design Spec

**Date:** 2026-06-12  
**Status:** Approved  
**Scope:** Python agent only — dashboard unchanged

---

## Goal

Allow the RMM agent to run on macOS (Intel and Apple Silicon) with the same feature set as Windows, using platform-native commands where Windows-specific tools are unavailable.

---

## Approach: Platform Abstraction Layer (Option A)

Each file uses `IS_WINDOWS` / `IS_MACOS` flags from a shared `platform_utils.py`. No separate executor files — all handlers live in the same files with explicit `if IS_WINDOWS / else` branches. This keeps the dispatch table and `execute_command()` logic unchanged.

---

## 1. New File: `agent/platform_utils.py`

```python
import platform
IS_WINDOWS = platform.system() == "Windows"
IS_MACOS   = platform.system() == "Darwin"
```

Imported by `hardware.py`, `executor.py`, `snapshot.py`. Replaces all inline `platform.system()` checks.

---

## 2. `agent/hardware.py` Changes

Every Windows-specific call gets a macOS branch. All functions retain the same signature and return `None`/default on failure — never raise.

| Function | Windows | macOS |
|---|---|---|
| `get_serial_number` | `wmic bios get SerialNumber` | `system_profiler SPHardwareDataType` → Hardware UUID |
| `get_cpu_name` | `wmic cpu get Name` | `sysctl -n machdep.cpu.brand_string` |
| `get_cpu_temp` | WMI `MSAcpi_ThermalZoneTemperature` | `None` (Apple Silicon does not expose thermal via CLI) |
| `get_storage_info` | `psutil.disk_usage("C:\\")` | `psutil.disk_usage("/")` |
| `get_firewall_status` | `netsh advfirewall show allprofiles` | `/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate` |
| `get_antivirus_status` | WMI `SecurityCenter2` | Return `"XProtect (built-in)"` |
| `get_cpu_usage` / `get_ram_*` | `psutil` — unchanged | `psutil` — unchanged |
| `get_os_info` | `platform.system/release/version` — unchanged | same |

`collect_all()` — no changes needed; calls the same functions.

`subprocess.STARTUPINFO` (hide window) is Windows-only — wrap in `if IS_WINDOWS` before constructing.

---

## 3. `agent/executor.py` Changes

### 3a. `_hidden_startupinfo()` and `_run()`

`STARTUPINFO` is Windows-only. On macOS, `_run()` calls `subprocess.run()` without `startupinfo`.

```python
def _run(args, timeout=COMMAND_TIMEOUT, shell=False):
    kwargs = dict(capture_output=True, text=True, timeout=timeout, shell=shell)
    if IS_WINDOWS:
        kwargs["startupinfo"] = _hidden_startupinfo()
    result = subprocess.run(args, **kwargs)
    ...
```

### 3b. `_ps()` helper — Windows only

macOS handlers call shell commands directly via `_run()`. No PowerShell equivalent needed.

### 3c. `_find_anydesk()` — add macOS path

```
/Applications/AnyDesk.app/Contents/MacOS/AnyDesk
```

`winreg` import wrapped in `if IS_WINDOWS`.

### 3d. Command handler mapping

| command_type | macOS implementation |
|---|---|
| `kill_process` | `pkill -9 <name>` — strips `.exe` suffix if present |
| `list_processes` | `psutil` (cross-platform, no change) |
| `reboot` | `sudo shutdown -r now` |
| `shutdown` | `sudo shutdown -h now` |
| `custom_cmd` | `bash -c <command>` |
| `get_system_info` | `sw_vers` + `sysctl -n kern.boottime` + `uptime` |
| `list_installed_software` | `system_profiler SPApplicationsDataType -json` |
| `uninstall_software` | `rm -rf /Applications/<app>.app` — validates name contains no path separators |
| `get_event_logs` | `log show --last 24h --predicate 'eventType == faultEvent' --style compact` |
| `run_sfc` | `diskutil verifyVolume /` |
| `flush_dns` | `dscacheutil -flushcache && killall -HUP mDNSResponder` |
| `clear_temp` | `rm -rf /tmp/* ~/Library/Caches/*` via subprocess |
| `get_network_info` | `ifconfig` |
| `ping_test` | `ping -c 4 <host>` |
| `lock_screen` | `pmset displaysleepnow` |
| `enable_rdp` | `systemsetup -setremotelogin on` |
| `disable_rdp` | `systemsetup -setremotelogin off` |
| `get_bitlocker_status` | `fdesetup status` |
| `enable_bitlocker` | `fdesetup enable` (ignores `drive` payload — macOS encrypts whole disk) |
| `disable_bitlocker` | `fdesetup disable` |
| `run_defender_scan` | Return `"Not supported on macOS — XProtect runs automatically"` |
| `disk_cleanup` | `periodic daily weekly monthly` |
| `windows_update` | `softwareupdate -ia` |
| `get_hardware_devices` | `system_profiler SPUSBDataType SPPCIDataType -json` |
| `get_anydesk_id` | Same logic — finds AnyDesk at macOS path |
| `take_snapshot` | Unchanged — see section 4 |

`COMMAND_HANDLERS` dispatch table — no structural changes. Each handler detects platform internally.

---

## 4. `agent/snapshot.py` Changes

`mss` is cross-platform — no change to capture logic.

Path validation: currently rejects non-absolute paths. Add platform-aware hint in log message only:
- Windows: path should start with `\\` or drive letter
- macOS: path should start with `/Volumes/` or `/`

Admin is responsible for mounting the SMB share before the agent runs (via Finder, `/etc/fstab`, or `mount_smbfs`). Agent writes to the mounted path directly — no credential handling.

No DB schema changes — `snapshot_share_path` stores whatever absolute path is valid for that device's OS.

---

## 5. Service / Startup

### Windows (unchanged)
NSSM Windows Service — no changes.

### macOS — LaunchDaemon
New file: `agent/macos/com.rmm.agent.plist`

- Installed to `/Library/LaunchDaemons/` (runs as root, auto-starts on boot)
- `RunAtLoad = true`, `KeepAlive = true`
- Working directory: wherever agent is installed (e.g. `/opt/rmm-agent`)
- Manual: `launchctl load /Library/LaunchDaemons/com.rmm.agent.plist`
- Direct run still works: `python main.py`

---

## 6. `requirements.txt` Changes

```
# Windows only — do not install on macOS
wmi==1.5.1        # windows
pywin32==306      # windows
pyinstaller==6.x  # windows (build tool)

# Cross-platform
supabase==2.x
psutil==5.x
mss==9.x
pystray==0.19.x   # supports macOS
Pillow==10.x
```

Add `requirements-macos.txt` excluding wmi/pywin32/pyinstaller, for macOS install clarity.

---

## 7. Out of Scope

- Dashboard changes — no changes needed; commands are sent the same way regardless of OS
- Linux support — not in scope
- Auto-mounting SMB share — admin responsibility
- `cpu_temp` on Apple Silicon — returns `None`, dashboard handles gracefully already

---

## Files Changed

| File | Change type |
|---|---|
| `agent/platform_utils.py` | New |
| `agent/hardware.py` | Modify — platform branches in 4 functions |
| `agent/executor.py` | Modify — platform branches in ~15 handlers |
| `agent/snapshot.py` | Modify — minor path validation tweak |
| `agent/macos/com.rmm.agent.plist` | New |
| `requirements.txt` | Modify — add comments |
| `requirements-macos.txt` | New |
