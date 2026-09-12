import json
import unittest

from huelightperfmon.hue import HueApiClient, HueApiError, HueLinkButtonRequired, HuePairingClient


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


class HueApiClientTests(unittest.TestCase):
    def test_lists_lights_sorted_by_name(self) -> None:
        opener = FakeOpener({"2": {"name": "Office"}, "1": {"name": "Desk"}})
        client = HueApiClient("192.0.2.1", "my token", opener=opener)

        lights = client.get_lights()

        self.assertEqual([(light.id, light.name) for light in lights], [("1", "Desk"), ("2", "Office")])
        request, options = opener.requests[0]
        self.assertEqual(request.full_url, "https://192.0.2.1/api/my%20token/lights")
        self.assertEqual(options["timeout"], 5.0)
        self.assertFalse(options["context"].check_hostname)

    def test_can_enable_strict_tls_verification(self) -> None:
        opener = FakeOpener({})
        HueApiClient("bridge", "token", verify_tls=True, opener=opener).get_lights()
        _request, options = opener.requests[0]
        self.assertTrue(options["context"].check_hostname)

    def test_sends_clamped_v1_light_state(self) -> None:
        opener = FakeOpener([{"success": {"/lights/3/state/on": True}}])
        client = HueApiClient("http://bridge/", "token", opener=opener)

        client.set_light_state("3", hue=70000, saturation=-2, brightness=0, transition_seconds=0.45)

        request, _options = opener.requests[0]
        self.assertEqual(request.method, "PUT")
        self.assertEqual(
            json.loads(request.data),
            {"on": True, "hue": 65535, "sat": 0, "bri": 1, "transitiontime": 4},
        )

    def test_surfaces_hue_error_from_http_200_response(self) -> None:
        opener = FakeOpener([{"error": {"type": 1, "description": "unauthorized user"}}])
        client = HueApiClient("bridge", "bad-token", opener=opener)

        with self.assertRaisesRegex(HueApiError, "unauthorized user"):
            client.get_lights()


class HuePairingClientTests(unittest.TestCase):
    def test_creates_application_token(self) -> None:
        opener = FakeOpener([{"success": {"username": "generated-token"}}])
        client = HuePairingClient("192.0.2.1", opener=opener)

        token = client.create_application_token("huelightperfmon#test-pc")

        self.assertEqual(token, "generated-token")
        request, _options = opener.requests[0]
        self.assertEqual(request.full_url, "https://192.0.2.1/api")
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {"devicetype": "huelightperfmon#test-pc"})

    def test_reports_required_physical_button(self) -> None:
        opener = FakeOpener([{"error": {"type": 101, "description": "link button not pressed"}}])
        client = HuePairingClient("bridge", opener=opener)

        with self.assertRaises(HueLinkButtonRequired):
            client.create_application_token()


if __name__ == "__main__":
    unittest.main()
