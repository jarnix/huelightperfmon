from __future__ import annotations

import json
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class HueApiError(RuntimeError):
    """A network, protocol, or Hue bridge error."""


class HueLinkButtonRequired(HueApiError):
    """The bridge rejected pairing because its physical button was not pressed."""


@dataclass(frozen=True, slots=True)
class HueLight:
    id: str
    name: str


class HueApiClient:
    def __init__(
        self,
        bridge_url: str,
        token: str,
        *,
        verify_tls: bool = False,
        timeout: float = 5.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        bridge_url = normalize_bridge_url(bridge_url)
        self._api_url = f"{bridge_url}/api/{quote(token.strip(), safe='')}"
        self._verify_tls = verify_tls
        self._timeout = timeout
        self._opener = opener

    def get_lights(self) -> list[HueLight]:
        payload = self._request("GET", "/lights")
        if not isinstance(payload, dict):
            raise HueApiError("The bridge returned an unexpected lights response.")
        lights = [
            HueLight(id=str(light_id), name=str(details.get("name", f"Light {light_id}")))
            for light_id, details in payload.items()
            if isinstance(details, dict)
        ]
        return sorted(lights, key=lambda light: light.name.casefold())

    def set_light_state(
        self,
        light_id: str,
        *,
        hue: int,
        saturation: int,
        brightness: int,
        transition_seconds: float,
    ) -> None:
        state = {
            "on": True,
            "hue": max(0, min(65535, int(hue))),
            "sat": max(0, min(254, int(saturation))),
            "bri": max(1, min(254, int(brightness))),
            "transitiontime": max(0, min(300, round(transition_seconds * 10))),
        }
        self._request("PUT", f"/lights/{quote(str(light_id), safe='')}/state", state)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        encoded = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self._api_url}{path}",
            data=encoded,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        result = _perform_json_request(
            request,
            verify_tls=self._verify_tls,
            timeout=self._timeout,
            opener=self._opener,
        )
        error = _find_hue_error(result)
        if error:
            raise HueApiError(error)
        return result


class HuePairingClient:
    def __init__(
        self,
        bridge_url: str,
        *,
        verify_tls: bool = False,
        timeout: float = 5.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self._bridge_url = normalize_bridge_url(bridge_url)
        self._verify_tls = verify_tls
        self._timeout = timeout
        self._opener = opener

    def create_application_token(self, device_type: str | None = None) -> str:
        device_type = device_type or _default_device_type()
        request = Request(
            f"{self._bridge_url}/api",
            data=json.dumps({"devicetype": device_type}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        result = _perform_json_request(
            request,
            verify_tls=self._verify_tls,
            timeout=self._timeout,
            opener=self._opener,
        )
        error_details = _find_hue_error_details(result)
        if error_details:
            error_type, description = error_details
            if error_type == 101:
                raise HueLinkButtonRequired("Press the link button on the Hue bridge.")
            raise HueApiError(f"Hue bridge error: {description}")
        if isinstance(result, list):
            for item in result:
                if not isinstance(item, dict) or not isinstance(item.get("success"), dict):
                    continue
                username = item["success"].get("username")
                if isinstance(username, str) and username:
                    return username
        raise HueApiError("The bridge paired but did not return an application token.")


def normalize_bridge_url(bridge_url: str) -> str:
    bridge_url = bridge_url.strip().rstrip("/")
    if not bridge_url.startswith(("http://", "https://")):
        bridge_url = f"https://{bridge_url}"
    return bridge_url


def _perform_json_request(
    request: Request,
    *,
    verify_tls: bool,
    timeout: float,
    opener: Callable[..., Any],
) -> Any:
    try:
        context = None
        if request.full_url.startswith("https://"):
            context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
        with opener(request, timeout=timeout, context=context) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise HueApiError(f"Hue bridge returned HTTP {exc.code}.") from exc
    except (URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise HueApiError(f"Could not contact Hue bridge: {reason}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise HueApiError("Hue bridge returned invalid JSON.") from exc


def _find_hue_error(payload: Any) -> str | None:
    details = _find_hue_error_details(payload)
    if details:
        return f"Hue bridge error: {details[1]}"
    return None


def _find_hue_error_details(payload: Any) -> tuple[int | None, str] | None:
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("error"), dict):
            error = item["error"]
            description = error.get("description", "Unknown bridge error")
            error_type = error.get("type")
            return (error_type if isinstance(error_type, int) else None, str(description))
    return None


def _default_device_type() -> str:
    computer_name = re.sub(r"[^A-Za-z0-9_-]", "-", socket.gethostname()).strip("-") or "windows-pc"
    return f"huelightperfmon#{computer_name[:20]}"
