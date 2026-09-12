from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox
from typing import Callable

import pystray
from PIL import Image, ImageDraw

from huelightperfmon.config import AppConfig, ConfigError, ConfigStore, app_data_directory
from huelightperfmon.controller import ControllerStatus, LightController
from huelightperfmon.sensors import create_default_registry
from huelightperfmon.ui import ConfigurationWindow


LOGGER = logging.getLogger(__name__)


class TrayApplication:
    def __init__(self) -> None:
        self._setup_logging()
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.title("Hue Light Performance Monitor")
        self._ui_queue: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._config_lock = threading.Lock()
        self._store = ConfigStore()
        self._load_error: str | None = None
        try:
            self._config = self._store.load()
        except ConfigError as exc:
            LOGGER.exception("Configuration could not be loaded")
            self._config = AppConfig()
            self._load_error = str(exc)

        self._sensors = create_default_registry()
        self._controller = LightController(self.get_config, self._sensors, self._controller_status_changed)
        self._icon = pystray.Icon(
            "HueLightPerfMon",
            _create_tray_image(),
            "Hue Light Performance Monitor",
            self._create_menu(),
        )
        self._config_window: ConfigurationWindow | None = None
        self._shutting_down = False

    def run(self) -> None:
        self._root.after(100, self._drain_ui_queue)
        if self._load_error:
            self._root.after(250, self._show_load_error)
        elif not self.get_config().is_ready:
            self._root.after(250, self.open_settings)
        self._controller.start(self.get_config().enabled)
        threading.Thread(target=self._icon.run, name="system-tray", daemon=True).start()
        try:
            self._root.mainloop()
        finally:
            self._shutdown_components()

    def get_config(self) -> AppConfig:
        with self._config_lock:
            return self._config

    def apply_config(self, config: AppConfig) -> None:
        with self._config_lock:
            self._config = config
        self._controller.notify_config_changed()
        self._controller.set_active(config.enabled)
        self._safe_update_menu()

    def schedule_ui(self, callback: Callable[[], None]) -> None:
        self._ui_queue.put(callback)

    def open_settings(self) -> None:
        if self._config_window and self._config_window.window.winfo_exists():
            self._config_window.window.lift()
            self._config_window.window.focus_force()
            return
        self._config_window = ConfigurationWindow(
            self._root,
            self.get_config(),
            self._store,
            self._sensors,
            self.apply_config,
            self.schedule_ui,
            self._settings_closed,
        )

    def set_monitoring(self, enabled: bool) -> None:
        config = replace(self.get_config(), enabled=enabled)
        try:
            self._store.save(config)
        except ConfigError as exc:
            LOGGER.error("Could not persist monitoring state: %s", exc)
        with self._config_lock:
            self._config = config
        self._controller.set_active(enabled)
        self._safe_update_menu()

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._root.quit()

    def _create_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda _item: self._controller.status.menu_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings…", lambda _icon, _item: self.schedule_ui(self.open_settings), default=True),
            pystray.MenuItem(
                "Start monitoring",
                lambda _icon, _item: self.schedule_ui(lambda: self.set_monitoring(True)),
                enabled=lambda _item: not self._controller.active and self.get_config().is_ready,
            ),
            pystray.MenuItem(
                "Stop monitoring",
                lambda _icon, _item: self.schedule_ui(lambda: self.set_monitoring(False)),
                enabled=lambda _item: self._controller.active,
            ),
            pystray.MenuItem("Open config folder", lambda _icon, _item: self._open_config_folder()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda _icon, _item: self.schedule_ui(self.shutdown)),
        )

    def _controller_status_changed(self, _status: ControllerStatus) -> None:
        self._safe_update_menu()

    def _safe_update_menu(self) -> None:
        try:
            self._icon.update_menu()
        except Exception:
            LOGGER.debug("Tray menu is not ready for an update", exc_info=True)

    def _open_config_folder(self) -> None:
        try:
            folder = app_data_directory()
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)  # type: ignore[attr-defined]
        except OSError:
            LOGGER.exception("Could not open configuration folder")

    def _drain_ui_queue(self) -> None:
        while True:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:
                LOGGER.exception("UI callback failed")
        if not self._shutting_down:
            self._root.after(100, self._drain_ui_queue)

    def _settings_closed(self) -> None:
        self._config_window = None

    def _show_load_error(self) -> None:
        messagebox.showerror(
            "Configuration error",
            f"The saved configuration could not be loaded. Defaults will be shown.\n\n{self._load_error}",
            parent=self._root,
        )
        self.open_settings()

    def _shutdown_components(self) -> None:
        self._controller.shutdown()
        try:
            self._icon.stop()
        except Exception:
            LOGGER.debug("Tray icon was already stopped", exc_info=True)
        try:
            self._root.destroy()
        except tk.TclError:
            pass

    @staticmethod
    def _setup_logging() -> None:
        local_app_data = os.environ.get("LOCALAPPDATA")
        log_dir = Path(local_app_data) / "HueLightPerfMon" if local_app_data else app_data_directory()
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            logging.basicConfig(
                filename=log_dir / "huelightperfmon.log",
                level=logging.INFO,
                format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            )
        except OSError:
            logging.basicConfig(level=logging.INFO)


def _create_tray_image(size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (24, 27, 34, 255))
    draw = ImageDraw.Draw(image)
    for y in range(8, 47):
        fraction = (y - 8) / 39
        color = (round(50 + 205 * fraction), round(215 - 150 * fraction), 65, 255)
        inset = abs(y - 27) // 3
        draw.line((15 + inset, y, 49 - inset, y), fill=color, width=2)
    draw.rounded_rectangle((25, 43, 39, 54), radius=3, fill=(225, 228, 235, 255))
    draw.line((27, 57, 37, 57), fill=(225, 228, 235, 255), width=3)
    return image


def main() -> None:
    TrayApplication().run()

