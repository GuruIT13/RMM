"""Test hardware module for macOS support."""
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
