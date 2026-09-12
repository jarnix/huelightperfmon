from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import psutil


@dataclass(frozen=True, slots=True)
class SensorDefinition:
    key: str
    label: str
    unit: str
    reader: Callable[[], float]


class SensorRegistry:
    """Registry that makes additional local sensors easy to add later."""

    def __init__(self) -> None:
        self._sensors: dict[str, SensorDefinition] = {}

    def register(self, sensor: SensorDefinition) -> None:
        self._sensors[sensor.key] = sensor

    def get(self, key: str) -> SensorDefinition:
        try:
            return self._sensors[key]
        except KeyError as exc:
            raise KeyError(f"Unknown sensor: {key}") from exc

    def all(self) -> tuple[SensorDefinition, ...]:
        return tuple(self._sensors.values())


def create_default_registry() -> SensorRegistry:
    registry = SensorRegistry()
    registry.register(
        SensorDefinition(
            key="cpu_total",
            label="CPU load (total)",
            unit="%",
            reader=lambda: float(psutil.cpu_percent(interval=None)),
        )
    )
    # Prime psutil's non-blocking CPU counter. The controller's first real reading
    # happens after the GUI and tray have started.
    psutil.cpu_percent(interval=None)
    return registry

