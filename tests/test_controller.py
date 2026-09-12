import threading
import unittest
from unittest.mock import patch

from huelightperfmon.config import AppConfig
from huelightperfmon.controller import LightController
from huelightperfmon.sensors import SensorDefinition, SensorRegistry


class FakeHueClient:
    updated = threading.Event()
    last_state = None

    def __init__(self, bridge_url, token, *, verify_tls=False):
        self.connection = (bridge_url, token, verify_tls)

    def set_light_state(self, light_id, **state):
        type(self).last_state = (light_id, state)
        type(self).updated.set()


class LightControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeHueClient.updated.clear()
        FakeHueClient.last_state = None

    def test_reads_sensor_and_updates_configured_light(self) -> None:
        registry = SensorRegistry()
        registry.register(SensorDefinition("test", "Test sensor", "%", lambda: 50.0))
        config = AppConfig(
            bridge_url="bridge",
            token="token",
            light_id="9",
            sensor="test",
            brightness_min=20,
            brightness_max=100,
            update_seconds=0.2,
        )
        controller = LightController(lambda: config, registry)

        with patch("huelightperfmon.controller.HueApiClient", FakeHueClient):
            controller.start(active=True)
            self.assertTrue(FakeHueClient.updated.wait(1.0))
            controller.shutdown()

        light_id, state = FakeHueClient.last_state
        self.assertEqual(light_id, "9")
        self.assertEqual(state["brightness"], 152)
        self.assertEqual(controller.status.state, "Stopped")


if __name__ == "__main__":
    unittest.main()

