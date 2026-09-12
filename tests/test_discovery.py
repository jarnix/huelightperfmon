import json
import unittest
from unittest.mock import patch

from zeroconf import IPVersion, ServiceStateChange

from huelightperfmon.discovery import (
    HUE_MDNS_SERVICE,
    DiscoveredBridge,
    DiscoveryError,
    discover_cloud_bridges,
    discover_mdns_bridges,
)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._body


class FakeOpener:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.requests = []

    def __call__(self, request, **kwargs):
        self.requests.append((request, kwargs))
        return FakeResponse(self.payload)


class DiscoveredBridgeTests(unittest.TestCase):
    def test_formats_https_url_and_label(self) -> None:
        bridge = DiscoveredBridge("192.0.2.4", "001788ABCDEF", "Office bridge")
        self.assertEqual(bridge.url, "https://192.0.2.4")
        self.assertEqual(bridge.display_name, "Office bridge ABCDEF  [192.0.2.4]")

    def test_does_not_repeat_id_already_in_name(self) -> None:
        bridge = DiscoveredBridge("192.0.2.4", "001788ABCDEF", "Hue Bridge - ABCDEF")
        self.assertEqual(bridge.display_name, "Hue Bridge - ABCDEF  [192.0.2.4]")


class FakeServiceInfo:
    port = 443
    properties = {b"bridgeid": b"001788ABCDEF"}

    def parsed_addresses(self, version):
        if version is IPVersion.V4Only:
            return ["192.0.2.30"]
        return []


class FakeZeroconf:
    def __init__(self, **_kwargs):
        self.closed = False

    def get_service_info(self, service_type, name, timeout):
        return FakeServiceInfo()

    def close(self):
        self.closed = True


class FakeServiceBrowser:
    def __init__(self, zeroconf, service_type, handlers):
        handlers[0](
            zeroconf=zeroconf,
            service_type=service_type,
            name=f"Hue Bridge - ABCDEF.{HUE_MDNS_SERVICE}",
            state_change=ServiceStateChange.Added,
        )

    def cancel(self):
        pass


class MdnsDiscoveryTests(unittest.TestCase):
    def test_accepts_keyword_callback_and_extracts_bridge(self) -> None:
        with (
            patch("huelightperfmon.discovery.Zeroconf", FakeZeroconf),
            patch("huelightperfmon.discovery.ServiceBrowser", FakeServiceBrowser),
        ):
            bridges = discover_mdns_bridges(0.2)

        self.assertEqual(len(bridges), 1)
        self.assertEqual(bridges[0].address, "192.0.2.30")
        self.assertEqual(bridges[0].bridge_id, "001788ABCDEF")


class CloudDiscoveryTests(unittest.TestCase):
    def test_parses_and_deduplicates_bridge_addresses(self) -> None:
        opener = FakeOpener(
            [
                {"id": "bridge-one", "internalipaddress": "192.0.2.10"},
                {"id": "bridge-one", "internalipaddress": "192.0.2.10"},
                {"id": "bridge-two", "internalipaddress": "192.0.2.20", "port": 8443},
                {"id": "bad", "internalipaddress": "not-an-ip"},
            ]
        )

        bridges = discover_cloud_bridges(opener=opener)

        self.assertEqual([bridge.address for bridge in bridges], ["192.0.2.10", "192.0.2.20:8443"])
        request, options = opener.requests[0]
        self.assertEqual(request.full_url, "https://discovery.meethue.com/")
        self.assertEqual(options["timeout"], 4.0)

    def test_rejects_unexpected_response(self) -> None:
        with self.assertRaisesRegex(DiscoveryError, "unexpected"):
            discover_cloud_bridges(opener=FakeOpener({"not": "a list"}))


if __name__ == "__main__":
    unittest.main()
