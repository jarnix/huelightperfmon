from __future__ import annotations

import ipaddress
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from zeroconf import IPVersion, ServiceBrowser, ServiceStateChange, Zeroconf


LOGGER = logging.getLogger(__name__)
HUE_MDNS_SERVICE = "_hue._tcp.local."
HUE_DISCOVERY_URL = "https://discovery.meethue.com/"


class DiscoveryError(RuntimeError):
    """Raised when bridge discovery cannot be completed."""


@dataclass(frozen=True, slots=True)
class DiscoveredBridge:
    address: str
    bridge_id: str = ""
    name: str = "Philips Hue bridge"

    @property
    def url(self) -> str:
        return f"https://{self.address}"

    @property
    def display_name(self) -> str:
        short_id = self.bridge_id[-6:]
        identifier = f" {short_id}" if short_id and short_id.casefold() not in self.name.casefold() else ""
        return f"{self.name}{identifier}  [{self.address}]"


def discover_bridges(timeout: float = 3.0) -> list[DiscoveredBridge]:
    """Find bridges over local mDNS, with Hue's discovery service as fallback."""

    local_error: Exception | None = None
    try:
        local = discover_mdns_bridges(timeout)
    except Exception as exc:
        LOGGER.warning("Local Hue mDNS discovery failed", exc_info=True)
        local = []
        local_error = exc
    if local:
        return local

    try:
        return discover_cloud_bridges()
    except Exception as exc:
        LOGGER.warning("Hue discovery service failed", exc_info=True)
        if local_error:
            raise DiscoveryError(f"Local scan failed ({local_error}); Hue fallback failed ({exc}).") from exc
        raise DiscoveryError(f"No local bridge was found and the Hue fallback failed: {exc}") from exc


def discover_mdns_bridges(timeout: float = 3.0) -> list[DiscoveredBridge]:
    found: dict[str, DiscoveredBridge] = {}
    found_lock = threading.Lock()
    zeroconf = Zeroconf(ip_version=IPVersion.V4Only)

    def service_changed(
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change not in (ServiceStateChange.Added, ServiceStateChange.Updated):
            return
        info = zeroconf.get_service_info(service_type, name, timeout=1000)
        if info is None:
            return
        addresses = info.parsed_addresses(IPVersion.V4Only)
        if not addresses:
            return
        address = addresses[0]
        if info.port and info.port != 443:
            address = f"{address}:{info.port}"
        bridge_id = _property_text(info.properties, b"bridgeid")
        instance_name = name.removesuffix(HUE_MDNS_SERVICE).rstrip(".") or "Philips Hue bridge"
        bridge = DiscoveredBridge(address=address, bridge_id=bridge_id, name=instance_name)
        with found_lock:
            found[bridge.address] = bridge

    browser = ServiceBrowser(zeroconf, HUE_MDNS_SERVICE, handlers=[service_changed])
    try:
        threading.Event().wait(max(0.2, timeout))
    finally:
        browser.cancel()
        zeroconf.close()
    with found_lock:
        return sorted(found.values(), key=lambda bridge: (bridge.name.casefold(), bridge.address))


def discover_cloud_bridges(
    *,
    timeout: float = 4.0,
    opener: Callable[..., Any] = urlopen,
) -> list[DiscoveredBridge]:
    request = Request(HUE_DISCOVERY_URL, headers={"Accept": "application/json"})
    try:
        with opener(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise DiscoveryError(f"Hue discovery returned HTTP {exc.code}.") from exc
    except (URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise DiscoveryError(f"Could not contact Hue discovery: {reason}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DiscoveryError("Hue discovery returned invalid JSON.") from exc
    if not isinstance(payload, list):
        raise DiscoveryError("Hue discovery returned an unexpected response.")

    found: dict[str, DiscoveredBridge] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        address = str(item.get("internalipaddress", "")).strip()
        try:
            ipaddress.ip_address(address)
        except ValueError:
            continue
        port = item.get("port")
        if isinstance(port, int) and port not in (0, 443):
            address = f"{address}:{port}"
        bridge = DiscoveredBridge(address=address, bridge_id=str(item.get("id", "")))
        found[address] = bridge
    return sorted(found.values(), key=lambda bridge: bridge.address)


def _property_text(properties: dict[bytes, bytes | None], key: bytes) -> str:
    value = properties.get(key)
    if not value:
        return ""
    return value.decode("utf-8", errors="replace")
