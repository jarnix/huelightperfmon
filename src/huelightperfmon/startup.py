from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - only relevant when imported off Windows
    winreg = None  # type: ignore[assignment]


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "HueLightPerfMon"


class StartupError(RuntimeError):
    """Raised when the per-user Windows startup entry cannot be changed."""


def startup_command(
    executable: str | Path | None = None,
    *,
    frozen: bool | None = None,
) -> str:
    """Return the command Windows should launch for this installation."""
    executable_path = Path(executable or sys.executable).resolve()
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        arguments = [str(executable_path)]
    else:
        pythonw_path = executable_path.with_name("pythonw.exe")
        launcher = pythonw_path if pythonw_path.is_file() else executable_path
        arguments = [str(launcher), "-m", "huelightperfmon"]
    return subprocess.list2cmdline(arguments)


def set_start_with_windows(enabled: bool) -> None:
    """Create or remove this user's Windows Run registry value."""
    if winreg is None:
        raise StartupError("Start with Windows is only available on Windows.")

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE_NAME)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        action = "enable" if enabled else "disable"
        raise StartupError(f"Could not {action} Start with Windows: {exc}") from exc
