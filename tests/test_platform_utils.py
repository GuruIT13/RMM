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
