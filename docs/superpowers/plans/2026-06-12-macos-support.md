# macOS Support for RMM Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the RMM Python agent run on macOS (Intel + Apple Silicon M1/M2/M3) with the same command set as Windows, using macOS-native equivalents.

**Architecture:** Add `platform_utils.py` with `IS_WINDOWS`/`IS_MACOS` flags; refactor `hardware.py` and `executor.py` to branch per platform inside each function; add LaunchDaemon plist for macOS service install. No changes to dashboard or DB schema.

**Tech Stack:** Python 3.10+, psutil, mss, pystray, subprocess (no new deps for macOS)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `agent/platform_utils.py` | Create | OS detection flags |
| `agent/hardware.py` | Modify | Platform-aware hardware collection |
| `agent/executor.py` | Modify | Platform-aware command handlers |
| `agent/snapshot.py` | Modify | Improve path validation log message |
| `agent/macos/com.rmm.agent.plist` | Create | LaunchDaemon service definition |
| `agent/requirements.txt` | Modify | Add platform comments |
| `agent/requirements-macos.txt` | Create | macOS-only deps (excludes wmi/pywin32) |
| `tests/test_hardware_macos.py` | Create | macOS hardware function tests |
| `tests/test_executor_macos.py` | Create | macOS executor handler tests |

---

## Task 1: Create `platform_utils.py`

**Files:**
- Create: `agent/platform_utils.py`
- Create: `tests/test_platform_utils.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_platform_utils.py
import sys
from unittest import mock


def test_is_windows_true_on_windows():
    with mock.patch("platform.system", return_value="Windows"):
        import importlib
        import agent.platform_utils as pu
        importlib.reload(pu)
        assert pu.IS_WINDOWS is True
        assert pu.IS_MACOS is False


def test_is_macos_true_on_darwin():
    with mock.patch("platform.system", return_value="Darwin"):
        import importlib
        import agent.platform_utils as pu
        importlib.reload(pu)
        assert pu.IS_MACOS is True
        assert pu.IS_WINDOWS is False
```

- [ ] **Step 2: Run test to verify it fails**

```
cd agent
python -m pytest ../tests/test_platform_utils.py -v
```
Expected: `ModuleNotFoundError: No module named 'agent.platform_utils'`

- [ ] **Step 3: Create `agent/platform_utils.py`**

```python
import platform

IS_WINDOWS: bool = platform.system() == "Windows"
IS_MACOS: bool = platform.system() == "Darwin"
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m pytest ../tests/test_platform_utils.py -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add agent/platform_utils.py tests/test_platform_utils.py
git commit -m "feat(agent): add platform_utils with IS_WINDOWS/IS_MACOS flags"
```

---

## Task 2: Refactor `hardware.py` — serial number + CPU name

**Files:**
- Modify: `agent/hardware.py`
- Create: `tests/test_hardware_macos.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_hardware_macos.py
from unittest import mock
import subprocess


def test_get_serial_number_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    mock_result = mock.MagicMock()
    mock_result.stdout = (
        "Hardware Overview:\n"
        "  Hardware UUID: AABB-1234-CCDD\n"
        "  Serial Number (system): C02XG1ABJGH5\n"
    )
    with mock.patch("subprocess.run", return_value=mock_result):
        from importlib import reload
        import agent.hardware as hw
        reload(hw)
        serial = hw.get_serial_number()
    assert serial == "C02XG1ABJGH5"


def test_get_cpu_name_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    mock_result = mock.MagicMock()
    mock_result.stdout = "Apple M1 Pro\n"
    with mock.patch("subprocess.run", return_value=mock_result):
        from importlib import reload
        import agent.hardware as hw
        reload(hw)
        name = hw.get_cpu_name()
    assert name == "Apple M1 Pro"
```

- [ ] **Step 2: Run to verify fails**

```
python -m pytest ../tests/test_hardware_macos.py::test_get_serial_number_macos -v
```
Expected: FAIL (functions still use wmic)

- [ ] **Step 3: Refactor `get_serial_number` and `get_cpu_name` in `agent/hardware.py`**

Replace the top of `hardware.py` imports section — add:
```python
from platform_utils import IS_WINDOWS, IS_MACOS
```

Replace `get_serial_number`:
```python
def get_serial_number() -> str:
    try:
        if IS_WINDOWS:
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
        elif IS_MACOS:
            result = subprocess.run(
                ["system_profiler", "SPHardwareDataType"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                if "Serial Number" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        serial = parts[1].strip()
                        if serial:
                            return serial
    except Exception as e:
        logger.warning("get_serial_number failed: %s", e)
    return platform.node()
```

Replace `get_cpu_name`:
```python
def get_cpu_name() -> Optional[str]:
    try:
        if IS_WINDOWS:
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
        elif IS_MACOS:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=10
            )
            name = result.stdout.strip()
            return name or None
    except Exception as e:
        logger.warning("get_cpu_name failed: %s", e)
    return None
```

- [ ] **Step 4: Run tests**

```
python -m pytest ../tests/test_hardware_macos.py -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add agent/hardware.py tests/test_hardware_macos.py
git commit -m "feat(agent): macOS serial number and CPU name via system_profiler/sysctl"
```

---

## Task 3: Refactor `hardware.py` — storage, firewall, antivirus, cpu_temp

**Files:**
- Modify: `agent/hardware.py`
- Modify: `tests/test_hardware_macos.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_hardware_macos.py`:
```python
def test_get_storage_info_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    import psutil
    fake_usage = mock.MagicMock()
    fake_usage.total = 500_000_000_000
    fake_usage.free = 200_000_000_000
    with mock.patch("psutil.disk_usage", return_value=fake_usage) as m:
        from importlib import reload
        import agent.hardware as hw
        reload(hw)
        total, free = hw.get_storage_info()
        m.assert_called_with("/")
    assert total == 500_000_000_000
    assert free == 200_000_000_000


def test_get_firewall_status_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    mock_result = mock.MagicMock()
    mock_result.stdout = "Firewall is enabled. (State = 1)\n"
    with mock.patch("subprocess.run", return_value=mock_result):
        from importlib import reload
        import agent.hardware as hw
        reload(hw)
        status = hw.get_firewall_status()
    assert status is True


def test_get_antivirus_status_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.hardware as hw
    reload(hw)
    status = hw.get_antivirus_status()
    assert status == "XProtect (built-in)"


def test_get_cpu_temp_macos_returns_none(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.hardware as hw
    reload(hw)
    assert hw.get_cpu_temp() is None
```

- [ ] **Step 2: Run to verify fails**

```
python -m pytest ../tests/test_hardware_macos.py -v
```
Expected: new 4 tests FAIL

- [ ] **Step 3: Refactor remaining functions in `agent/hardware.py`**

Replace `get_cpu_temp`:
```python
def get_cpu_temp() -> Optional[float]:
    if IS_MACOS:
        return None  # Apple Silicon does not expose thermal via CLI
    try:
        import wmi  # type: ignore
        w = wmi.WMI(namespace="root/wmi")
        sensors = w.MSAcpi_ThermalZoneTemperature()
        if sensors:
            return (sensors[0].CurrentTemperature / 10.0) - 273.15
    except Exception as e:
        logger.debug("get_cpu_temp failed (expected if no WMI sensor): %s", e)
    return None
```

Replace `get_storage_info`:
```python
def get_storage_info() -> tuple[int, int]:
    root = "C:\\" if IS_WINDOWS else "/"
    try:
        usage = psutil.disk_usage(root)
        return usage.total, usage.free
    except Exception as e:
        logger.warning("get_storage_info failed: %s", e)
        return 0, 0
```

Replace `get_firewall_status`:
```python
def get_firewall_status() -> Optional[bool]:
    try:
        if IS_WINDOWS:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            result = subprocess.run(
                ["netsh", "advfirewall", "show", "allprofiles", "state"],
                capture_output=True, text=True, timeout=10, startupinfo=si
            )
            return "ON" in result.stdout.upper()
        elif IS_MACOS:
            result = subprocess.run(
                ["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"],
                capture_output=True, text=True, timeout=10
            )
            return "enabled" in result.stdout.lower()
    except Exception as e:
        logger.warning("get_firewall_status failed: %s", e)
    return None
```

Replace `get_antivirus_status`:
```python
def get_antivirus_status() -> Optional[str]:
    if IS_MACOS:
        return "XProtect (built-in)"
    try:
        import wmi  # type: ignore
        w = wmi.WMI(namespace="root/SecurityCenter2")
        products = w.AntiVirusProduct()
        if products:
            return products[0].displayName
    except Exception as e:
        logger.debug("get_antivirus_status failed: %s", e)
    return None
```

- [ ] **Step 4: Run all hardware tests**

```
python -m pytest ../tests/test_hardware_macos.py -v
```
Expected: all 6 passed

- [ ] **Step 5: Commit**

```bash
git add agent/hardware.py tests/test_hardware_macos.py
git commit -m "feat(agent): macOS storage, firewall, antivirus, cpu_temp in hardware.py"
```

---

## Task 4: Refactor `executor.py` — `_run()`, `_find_anydesk()`, `custom_cmd`

**Files:**
- Modify: `agent/executor.py`
- Create: `tests/test_executor_macos.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_executor_macos.py
from unittest import mock
import sys


def test_run_no_startupinfo_on_macos(monkeypatch):
    """_run() must not pass startupinfo on macOS."""
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    captured = {}
    def fake_run(args, **kwargs):
        captured.update(kwargs)
        r = mock.MagicMock()
        r.stdout = "ok"
        r.stderr = ""
        return r

    with mock.patch("subprocess.run", side_effect=fake_run):
        ex._run(["echo", "hi"])
    assert "startupinfo" not in captured


def test_find_anydesk_macos_path(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    # create fake AnyDesk binary
    macos_path = tmp_path / "AnyDesk"
    macos_path.write_text("fake")

    from importlib import reload
    import agent.executor as ex
    reload(ex)
    ex._ANYDESK_MACOS_PATH = str(macos_path)

    result = ex._find_anydesk()
    assert result == str(macos_path)


def test_custom_cmd_macos_uses_bash(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        r = mock.MagicMock(); r.stdout = "hello"; r.stderr = ""
        return r

    with mock.patch("subprocess.run", side_effect=fake_run):
        result = ex.handle_custom_cmd({"command": "echo hello"})

    assert calls[0] == ["bash", "-c", "echo hello"]
```

- [ ] **Step 2: Run to verify fails**

```
python -m pytest ../tests/test_executor_macos.py -v
```
Expected: 3 FAIL

- [ ] **Step 3: Refactor `agent/executor.py` — imports + `_run()` + `_find_anydesk()` + `handle_custom_cmd()`**

Add import at top of file (after existing imports):
```python
from platform_utils import IS_WINDOWS, IS_MACOS
```

Add macOS AnyDesk path constant near `_ANYDESK_SEARCH_PATHS`:
```python
_ANYDESK_MACOS_PATH = "/Applications/AnyDesk.app/Contents/MacOS/AnyDesk"
```

Replace `_find_anydesk()`:
```python
def _find_anydesk() -> Optional[str]:
    import os
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
```

Replace `_run()`:
```python
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
```

Replace `handle_custom_cmd()`:
```python
def handle_custom_cmd(payload: dict) -> str:
    command = payload.get("command", "").strip()
    if not command:
        return "ERROR: Empty command"
    if len(command) > _CUSTOM_CMD_MAX_LEN:
        return f"ERROR: Command exceeds {_CUSTOM_CMD_MAX_LEN} character limit"
    if IS_WINDOWS:
        return _run(["cmd.exe", "/c", command], timeout=COMMAND_TIMEOUT)
    return _run(["bash", "-c", command], timeout=COMMAND_TIMEOUT)
```

- [ ] **Step 4: Run tests**

```
python -m pytest ../tests/test_executor_macos.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add agent/executor.py tests/test_executor_macos.py
git commit -m "feat(agent): macOS _run(), _find_anydesk(), custom_cmd in executor.py"
```

---

## Task 5: Refactor `executor.py` — process + system commands

**Files:**
- Modify: `agent/executor.py`
- Modify: `tests/test_executor_macos.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_executor_macos.py`:
```python
def test_kill_process_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        r = mock.MagicMock(); r.stdout = "killed"; r.stderr = ""
        return r

    with mock.patch("subprocess.run", side_effect=fake_run):
        ex.handle_kill_process({"process_name": "Finder"})
    assert calls[0] == ["pkill", "-9", "Finder"]


def test_kill_process_macos_strips_exe(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    calls = []
    def fake_run(args, **kwargs):
        calls.append(args); r = mock.MagicMock(); r.stdout = ""; r.stderr = ""; return r

    with mock.patch("subprocess.run", side_effect=fake_run):
        ex.handle_kill_process({"process_name": "notepad.exe"})
    assert calls[0] == ["pkill", "-9", "notepad"]


def test_reboot_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    calls = []
    def fake_run(args, **kwargs):
        calls.append(args); r = mock.MagicMock(); r.stdout = ""; r.stderr = ""; return r

    with mock.patch("subprocess.run", side_effect=fake_run):
        ex.handle_reboot()
    assert calls[0] == ["sudo", "shutdown", "-r", "now"]


def test_ping_test_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    calls = []
    def fake_run(args, **kwargs):
        calls.append(args); r = mock.MagicMock(); r.stdout = "pong"; r.stderr = ""; return r

    with mock.patch("subprocess.run", side_effect=fake_run):
        ex.handle_ping_test({"host": "8.8.8.8"})
    assert calls[0] == ["ping", "-c", "4", "8.8.8.8"]
```

- [ ] **Step 2: Run to verify fails**

```
python -m pytest ../tests/test_executor_macos.py -v -k "kill or reboot or ping"
```
Expected: 4 FAIL

- [ ] **Step 3: Refactor handlers in `agent/executor.py`**

Replace `handle_kill_process()`:
```python
_PROCESS_NAME_WIN_RE = _re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,253}\.exe$', _re.IGNORECASE)
_PROCESS_NAME_MAC_RE = _re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._\- ]{0,253}$')

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
```

Replace `handle_reboot()`:
```python
def handle_reboot() -> str:
    if IS_WINDOWS:
        return _run(["shutdown", "/r", "/t", "0", "/f"])
    return _run(["sudo", "shutdown", "-r", "now"])
```

Replace `handle_shutdown()`:
```python
def handle_shutdown() -> str:
    if IS_WINDOWS:
        return _run(["shutdown", "/s", "/t", "0", "/f"])
    return _run(["sudo", "shutdown", "-h", "now"])
```

Replace `handle_ping_test()`:
```python
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
```

Replace `handle_lock_screen()`:
```python
def handle_lock_screen() -> str:
    if IS_WINDOWS:
        _ps("rundll32.exe user32.dll,LockWorkStation", timeout=5)
    else:
        _run(["pmset", "displaysleepnow"], timeout=5)
    return "Screen locked"
```

Also remove old `_PROCESS_NAME_RE` line (replaced by `_PROCESS_NAME_WIN_RE` and `_PROCESS_NAME_MAC_RE` above).

- [ ] **Step 4: Run tests**

```
python -m pytest ../tests/test_executor_macos.py -v
```
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add agent/executor.py tests/test_executor_macos.py
git commit -m "feat(agent): macOS kill_process, reboot, shutdown, ping, lock_screen"
```

---

## Task 6: Refactor `executor.py` — system info + software + network

**Files:**
- Modify: `agent/executor.py`
- Modify: `tests/test_executor_macos.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_executor_macos.py`:
```python
def test_get_system_info_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    def fake_run(args, **kwargs):
        r = mock.MagicMock()
        if args[0] == "sw_vers":
            r.stdout = "ProductName: macOS\nProductVersion: 14.0\n"
        else:
            r.stdout = "up 3 days"
        r.stderr = ""
        return r

    with mock.patch("subprocess.run", side_effect=fake_run):
        result = ex.handle_get_system_info()
    assert "macOS" in result


def test_flush_dns_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    calls = []
    def fake_run(args, **kwargs):
        calls.append(args); r = mock.MagicMock(); r.stdout = "ok"; r.stderr = ""; return r

    with mock.patch("subprocess.run", side_effect=fake_run):
        ex.handle_flush_dns()
    assert any("dscacheutil" in str(c) for c in calls)


def test_run_defender_scan_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    result = ex.handle_run_defender_scan()
    assert "XProtect" in result
```

- [ ] **Step 2: Run to verify fails**

```
python -m pytest ../tests/test_executor_macos.py -v -k "system_info or flush_dns or defender"
```
Expected: 3 FAIL

- [ ] **Step 3: Refactor handlers**

Replace `handle_get_system_info()`:
```python
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
```

Replace `handle_flush_dns()`:
```python
def handle_flush_dns() -> str:
    if IS_WINDOWS:
        return _run(["ipconfig", "/flushdns"], timeout=15)
    out1 = _run(["dscacheutil", "-flushcache"], timeout=15)
    out2 = _run(["sudo", "killall", "-HUP", "mDNSResponder"], timeout=15)
    return f"{out1}\n{out2}".strip()
```

Replace `handle_get_network_info()`:
```python
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
```

Replace `handle_run_defender_scan()`:
```python
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
```

Replace `handle_clear_temp()`:
```python
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
    out1 = _run(["sudo", "rm", "-rf", "/tmp/*"], timeout=30)
    import os
    cache_dir = os.path.expanduser("~/Library/Caches")
    out2 = _run(["rm", "-rf", cache_dir], timeout=30)
    return f"Temp cleared: /tmp and ~/Library/Caches"
```

- [ ] **Step 4: Run all executor tests**

```
python -m pytest ../tests/test_executor_macos.py -v
```
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add agent/executor.py tests/test_executor_macos.py
git commit -m "feat(agent): macOS system_info, flush_dns, network_info, defender, clear_temp"
```

---

## Task 7: Refactor `executor.py` — software, hardware devices, RDP/FileVault, event logs

**Files:**
- Modify: `agent/executor.py`
- Modify: `tests/test_executor_macos.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_executor_macos.py`:
```python
def test_list_installed_software_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    mock_result = mock.MagicMock()
    mock_result.stdout = '{"SPApplicationsDataType": []}'
    mock_result.stderr = ""
    with mock.patch("subprocess.run", return_value=mock_result):
        result = ex.handle_list_installed_software()
    assert "SPApplicationsDataType" in result


def test_get_bitlocker_status_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    mock_result = mock.MagicMock()
    mock_result.stdout = "FileVault is On.\n"
    mock_result.stderr = ""
    with mock.patch("subprocess.run", return_value=mock_result):
        result = ex.handle_get_bitlocker_status()
    assert "FileVault" in result


def test_enable_rdp_macos(monkeypatch):
    monkeypatch.setattr("agent.platform_utils.IS_WINDOWS", False)
    monkeypatch.setattr("agent.platform_utils.IS_MACOS", True)

    from importlib import reload
    import agent.executor as ex
    reload(ex)

    calls = []
    def fake_run(args, **kwargs):
        calls.append(args); r = mock.MagicMock(); r.stdout = ""; r.stderr = ""; return r

    with mock.patch("subprocess.run", side_effect=fake_run):
        ex.handle_enable_rdp()
    assert any("setremotelogin" in str(c) for c in calls)
```

- [ ] **Step 2: Run to verify fails**

```
python -m pytest ../tests/test_executor_macos.py -v -k "software or bitlocker or rdp"
```
Expected: 3 FAIL

- [ ] **Step 3: Refactor handlers**

Replace `handle_list_installed_software()`:
```python
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
```

Replace `handle_get_hardware_devices()`:
```python
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
```

Replace `handle_get_event_logs()`:
```python
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
```

Replace `handle_run_sfc()`:
```python
def handle_run_sfc() -> str:
    if IS_WINDOWS:
        return _run(["sfc", "/scannow"], timeout=600)
    return _run(["diskutil", "verifyVolume", "/"], timeout=120)
```

Replace `handle_disk_cleanup()`:
```python
def handle_disk_cleanup() -> str:
    if IS_WINDOWS:
        return _run(["cleanmgr.exe", "/sagerun:1"])
    return _run(["sudo", "periodic", "daily", "weekly", "monthly"], timeout=300)
```

Replace `handle_windows_update()`:
```python
def handle_windows_update() -> str:
    if IS_MACOS:
        return _run(["softwareupdate", "-ia"], timeout=1800)
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
```

Replace `handle_enable_rdp()`:
```python
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
```

Replace `handle_disable_rdp()`:
```python
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
```

Replace `handle_get_bitlocker_status()`:
```python
def handle_get_bitlocker_status() -> str:
    if IS_WINDOWS:
        script = (
            "Get-BitLockerVolume -ErrorAction SilentlyContinue | "
            "Select-Object MountPoint, VolumeStatus, EncryptionPercentage, ProtectionStatus | "
            "Format-Table -AutoSize | Out-String"
        )
        return _ps(script, timeout=15)
    return _run(["fdesetup", "status"], timeout=15)
```

Replace `handle_enable_bitlocker()`:
```python
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
```

Replace `handle_disable_bitlocker()`:
```python
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
```

Replace `handle_uninstall_software()`:
```python
def handle_uninstall_software(payload: dict) -> str:
    name = payload.get("name", "").strip()
    if not name:
        return "ERROR: Missing name in payload"
    if IS_WINDOWS:
        name = name.replace("'", "''")
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
    # macOS: only allow app name, no path separators
    import os
    if "/" in name or "\\" in name or ".." in name:
        return "ERROR: Invalid app name"
    app_path = f"/Applications/{name}.app"
    if not os.path.isdir(app_path):
        return f"ERROR: {app_path} not found"
    return _run(["sudo", "rm", "-rf", app_path], timeout=60)
```

- [ ] **Step 4: Run all executor tests**

```
python -m pytest ../tests/test_executor_macos.py -v
```
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add agent/executor.py tests/test_executor_macos.py
git commit -m "feat(agent): macOS software, hardware, RDP, FileVault, event logs, disk, updates"
```

---

## Task 8: Update `snapshot.py` path validation log

**Files:**
- Modify: `agent/snapshot.py`

- [ ] **Step 1: Update log message in `agent/snapshot.py`**

Replace the warning log in `take()`:
```python
    if not dest.is_absolute():
        if IS_WINDOWS:
            logger.warning("Snapshot share path is not absolute (expected \\\\server\\share or drive letter): %s", share_path)
        else:
            logger.warning("Snapshot share path is not absolute (expected /Volumes/share or /path): %s", share_path)
        return []
```

Add import at top of `snapshot.py`:
```python
from platform_utils import IS_WINDOWS, IS_MACOS
```

- [ ] **Step 2: Verify no functional change**

```
python -m pytest ../tests/ -v -k "snapshot"
```
Expected: existing snapshot tests still pass (or pass if none exist yet)

- [ ] **Step 3: Commit**

```bash
git add agent/snapshot.py
git commit -m "fix(agent): platform-aware snapshot path validation log message"
```

---

## Task 9: Create LaunchDaemon plist + requirements-macos.txt

**Files:**
- Create: `agent/macos/com.rmm.agent.plist`
- Create: `agent/requirements-macos.txt`
- Modify: `agent/requirements.txt`

- [ ] **Step 1: Create `agent/macos/com.rmm.agent.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rmm.agent</string>

    <key>ProgramArguments</key>
    <array>
        <string>/opt/rmm-agent/venv/bin/python</string>
        <string>/opt/rmm-agent/main.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/opt/rmm-agent</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/var/log/rmm-agent.log</string>

    <key>StandardErrorPath</key>
    <string>/var/log/rmm-agent-error.log</string>
</dict>
</plist>
```

Install commands (run manually by admin):
```bash
sudo cp agent/macos/com.rmm.agent.plist /Library/LaunchDaemons/
sudo launchctl load /Library/LaunchDaemons/com.rmm.agent.plist
```

- [ ] **Step 2: Create `agent/requirements-macos.txt`**

```
# macOS dependencies — excludes Windows-only packages
supabase==2.15.2
psutil==6.1.1
pystray==0.19.5
Pillow==11.1.0
requests==2.32.3
packaging==24.2
mss==9.0.2
```

- [ ] **Step 3: Update `agent/requirements.txt` — add platform comments**

Replace file content:
```
# Cross-platform
supabase==2.15.2
psutil==6.1.1
pystray==0.19.5
Pillow==11.1.0
requests==2.32.3
packaging==24.2
mss==9.0.2

# Windows only — do not install on macOS
pywin32==308
WMI==1.5.1
```

- [ ] **Step 4: Commit**

```bash
git add agent/macos/com.rmm.agent.plist agent/requirements-macos.txt agent/requirements.txt
git commit -m "feat(agent): add LaunchDaemon plist and macOS requirements file"
```

---

## Task 10: Final integration smoke test

**Files:** none (verification only)

- [ ] **Step 1: Run full test suite**

```
cd agent
python -m pytest ../tests/ -v
```
Expected: all tests pass, no import errors

- [ ] **Step 2: Verify no Windows imports leak on macOS path**

```python
# run this on macOS or with IS_WINDOWS=False mock
import platform_utils
platform_utils.IS_WINDOWS = False
platform_utils.IS_MACOS = True
import hardware
import executor
print("Import OK")
```

Expected: no ImportError for winreg/wmi

- [ ] **Step 3: Verify dispatch table unchanged**

```python
import executor
expected_keys = {
    "get_anydesk_id","disk_cleanup","windows_update","kill_process",
    "reboot","shutdown","custom_cmd","get_system_info","list_processes",
    "list_installed_software","get_event_logs","run_sfc","flush_dns",
    "clear_temp","get_network_info","ping_test","lock_screen","enable_rdp",
    "disable_rdp","get_bitlocker_status","enable_bitlocker","disable_bitlocker",
    "run_defender_scan","get_hardware_devices","uninstall_software","take_snapshot"
}
assert set(executor.COMMAND_HANDLERS.keys()) == expected_keys
print("Dispatch table OK")
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(agent): complete macOS cross-platform support"
```
