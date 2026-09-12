from __future__ import annotations

import colorsys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HueState:
    hue: int
    saturation: int
    brightness: int


def sensor_fraction(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        raise ValueError("maximum must be greater than minimum")
    return max(0.0, min(1.0, (value - minimum) / (maximum - minimum)))


def map_sensor_to_hue(
    value: float,
    sensor_minimum: float,
    sensor_maximum: float,
    low_color: str,
    high_color: str,
    brightness_minimum: int,
    brightness_maximum: int,
) -> HueState:
    fraction = sensor_fraction(value, sensor_minimum, sensor_maximum)
    low_h, low_s, _ = _hex_to_hsv(low_color)
    high_h, high_s, _ = _hex_to_hsv(high_color)

    # Follow the shortest direction around the circular hue wheel.
    hue_delta = ((high_h - low_h + 0.5) % 1.0) - 0.5
    hue = (low_h + fraction * hue_delta) % 1.0
    saturation = _lerp(low_s, high_s, fraction)
    brightness_percent = _lerp(brightness_minimum, brightness_maximum, fraction)

    return HueState(
        hue=round(hue * 65535),
        saturation=round(saturation * 254),
        brightness=max(1, min(254, round(brightness_percent * 254 / 100))),
    )


def _hex_to_hsv(color: str) -> tuple[float, float, float]:
    red = int(color[1:3], 16) / 255
    green = int(color[3:5], 16) / 255
    blue = int(color[5:7], 16) / 255
    return colorsys.rgb_to_hsv(red, green, blue)


def _lerp(start: float, end: float, fraction: float) -> float:
    return start + (end - start) * fraction

