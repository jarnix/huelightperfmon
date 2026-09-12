from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


APP_DIRECTORY_NAME = "HueLightPerfMon"
CONFIG_FILENAME = "config.json"


class ConfigError(ValueError):
    """Raised when application configuration is invalid or unreadable."""


@dataclass(frozen=True, slots=True)
class AppConfig:
    bridge_url: str = ""
    token: str = ""
    light_id: str = ""
    verify_tls: bool = False
    sensor: str = "cpu_total"
    sensor_min: float = 0.0
    sensor_max: float = 100.0
    low_color: str = "#00ff00"
    high_color: str = "#ff0000"
    brightness_min: int = 20
    brightness_max: int = 100
    update_seconds: float = 2.0
    transition_seconds: float = 0.4
    enabled: bool = True

    @property
    def is_ready(self) -> bool:
        return bool(self.bridge_url.strip() and self.token.strip() and self.light_id.strip())

    def validate(self, *, require_connection: bool = False) -> None:
        if require_connection and not self.is_ready:
            raise ConfigError("Bridge URL, application token, and Hue light are required.")
        if self.sensor_max <= self.sensor_min:
            raise ConfigError("Sensor maximum must be greater than sensor minimum.")
        if not 1 <= self.brightness_min <= 100:
            raise ConfigError("Minimum brightness must be between 1 and 100%.")
        if not 1 <= self.brightness_max <= 100:
            raise ConfigError("Maximum brightness must be between 1 and 100%.")
        if self.brightness_max < self.brightness_min:
            raise ConfigError("Maximum brightness must be at least minimum brightness.")
        if not 0.2 <= self.update_seconds <= 3600:
            raise ConfigError("Update interval must be between 0.2 and 3600 seconds.")
        if not 0 <= self.transition_seconds <= 30:
            raise ConfigError("Transition time must be between 0 and 30 seconds.")
        for label, value in (("Low color", self.low_color), ("High color", self.high_color)):
            if not _is_hex_color(value):
                raise ConfigError(f"{label} must use the form #RRGGBB.")

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> AppConfig:
        known_names = {field.name for field in fields(cls)}
        known_values = {key: value for key, value in values.items() if key in known_names}
        try:
            config = cls(**known_values)
            config.validate()
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Invalid configuration: {exc}") from exc
        return config


def _is_hex_color(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


def app_data_directory(environment: dict[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    base = env.get("APPDATA")
    if base:
        return Path(base) / APP_DIRECTORY_NAME
    return Path.home() / ".config" / APP_DIRECTORY_NAME


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_directory() / CONFIG_FILENAME

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Could not read {self.path}: {exc}") from exc
        if not isinstance(values, dict):
            raise ConfigError(f"Configuration in {self.path} must be a JSON object.")
        return AppConfig.from_dict(values)

    def save(self, config: AppConfig) -> None:
        config.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(asdict(config), temporary, indent=2)
                temporary.write("\n")
                temporary_name = temporary.name
            os.replace(temporary_name, self.path)
        except OSError as exc:
            if temporary_name:
                try:
                    Path(temporary_name).unlink(missing_ok=True)
                except OSError:
                    pass
            raise ConfigError(f"Could not save {self.path}: {exc}") from exc
