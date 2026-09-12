import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from huelightperfmon import startup


class StartupCommandTests(unittest.TestCase):
    def test_frozen_command_quotes_executable_path(self) -> None:
        executable = Path("C:/Program Files/Hue Light/HueLightPerfMon.exe")
        self.assertEqual(
            startup.startup_command(executable, frozen=True),
            subprocess.list2cmdline([str(executable.resolve())]),
        )

    def test_source_command_uses_pythonw_and_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "python.exe"
            pythonw = executable.with_name("pythonw.exe")
            pythonw.touch()
            self.assertEqual(
                startup.startup_command(executable, frozen=False),
                subprocess.list2cmdline([str(pythonw.resolve()), "-m", "huelightperfmon"]),
            )


class StartupRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = MagicMock()
        self.registry.HKEY_CURRENT_USER = object()
        self.registry.KEY_SET_VALUE = 2
        self.registry.REG_SZ = 1
        self.key = self.registry.CreateKeyEx.return_value.__enter__.return_value

    def test_enable_writes_current_launch_command(self) -> None:
        with patch.object(startup, "winreg", self.registry), patch.object(
            startup, "startup_command", return_value='"C:\\Apps\\HueLightPerfMon.exe"'
        ):
            startup.set_start_with_windows(True)

        self.registry.SetValueEx.assert_called_once_with(
            self.key,
            startup.RUN_VALUE_NAME,
            0,
            self.registry.REG_SZ,
            '"C:\\Apps\\HueLightPerfMon.exe"',
        )

    def test_disable_removes_only_the_app_value(self) -> None:
        with patch.object(startup, "winreg", self.registry):
            startup.set_start_with_windows(False)

        self.registry.DeleteValue.assert_called_once_with(self.key, startup.RUN_VALUE_NAME)


if __name__ == "__main__":
    unittest.main()
