from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from huelightperfmon.colors import map_sensor_to_hue
from huelightperfmon.config import AppConfig
from huelightperfmon.hue import HueApiClient
from huelightperfmon.sensors import SensorRegistry


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ControllerStatus:
    state: str
    detail: str
    updated_at: datetime | None = None

    @property
    def menu_text(self) -> str:
        if self.detail:
            return f"{self.state}: {self.detail}"
        return self.state


class LightController:
    def __init__(
        self,
        config_provider: Callable[[], AppConfig],
        sensors: SensorRegistry,
        status_callback: Callable[[ControllerStatus], None] | None = None,
    ) -> None:
        self._config_provider = config_provider
        self._sensors = sensors
        self._status_callback = status_callback
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._active_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._status_lock = threading.Lock()
        self._status = ControllerStatus("Starting", "")
        self._client_key: tuple[str, str, bool] | None = None
        self._client: HueApiClient | None = None

    @property
    def active(self) -> bool:
        return self._active_event.is_set()

    @property
    def status(self) -> ControllerStatus:
        with self._status_lock:
            return self._status

    def start(self, active: bool) -> None:
        if self._thread and self._thread.is_alive():
            self.set_active(active)
            return
        if active:
            self._active_event.set()
        self._thread = threading.Thread(target=self._run, name="hue-controller", daemon=True)
        self._thread.start()

    def set_active(self, active: bool) -> None:
        if active:
            self._active_event.set()
        else:
            self._active_event.clear()
        self._wake_event.set()

    def notify_config_changed(self) -> None:
        self._client_key = None
        self._client = None
        self._wake_event.set()

    def shutdown(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            if not self.active:
                self._set_status("Paused", "monitoring is stopped")
                self._wait(3600)
                continue

            config = self._config_provider()
            if not config.is_ready:
                self._set_status("Configuration needed", "open Settings")
                self._wait(2.0)
                continue

            try:
                sensor = self._sensors.get(config.sensor)
                value = sensor.reader()
                target = map_sensor_to_hue(
                    value,
                    config.sensor_min,
                    config.sensor_max,
                    config.low_color,
                    config.high_color,
                    config.brightness_min,
                    config.brightness_max,
                )
                client = self._get_client(config)
                client.set_light_state(
                    config.light_id,
                    hue=target.hue,
                    saturation=target.saturation,
                    brightness=target.brightness,
                    transition_seconds=config.transition_seconds,
                )
                self._set_status(
                    "Running",
                    f"{sensor.label} {value:.1f}{sensor.unit}",
                    datetime.now(),
                )
            except Exception as exc:
                LOGGER.exception("Could not update Hue light")
                self._set_status("Error", str(exc))

            self._wait(config.update_seconds)

        self._set_status("Stopped", "")

    def _get_client(self, config: AppConfig) -> HueApiClient:
        key = (config.bridge_url, config.token, config.verify_tls)
        if self._client is None or self._client_key != key:
            self._client = HueApiClient(config.bridge_url, config.token, verify_tls=config.verify_tls)
            self._client_key = key
        return self._client

    def _wait(self, timeout: float) -> None:
        self._wake_event.wait(timeout)
        self._wake_event.clear()

    def _set_status(
        self,
        state: str,
        detail: str,
        updated_at: datetime | None = None,
    ) -> None:
        status = ControllerStatus(state, detail, updated_at)
        with self._status_lock:
            if status == self._status:
                return
            self._status = status
        if self._status_callback:
            try:
                self._status_callback(status)
            except Exception:
                LOGGER.exception("Status callback failed")
