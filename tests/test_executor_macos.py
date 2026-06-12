from unittest import mock
import sys


def test_run_no_startupinfo_on_macos(monkeypatch):
    """_run() must not pass startupinfo on macOS."""
    from importlib import reload
    import platform_utils

    monkeypatch.setattr(platform_utils, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_utils, "IS_MACOS", True)

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
    from importlib import reload
    import platform_utils

    monkeypatch.setattr(platform_utils, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_utils, "IS_MACOS", True)

    # create fake AnyDesk binary
    macos_path = tmp_path / "AnyDesk"
    macos_path.write_text("fake")

    import agent.executor as ex
    reload(ex)
    ex._ANYDESK_MACOS_PATH = str(macos_path)

    result = ex._find_anydesk()
    assert result == str(macos_path)


def test_custom_cmd_macos_uses_bash(monkeypatch):
    from importlib import reload
    import platform_utils

    monkeypatch.setattr(platform_utils, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_utils, "IS_MACOS", True)

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
