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
