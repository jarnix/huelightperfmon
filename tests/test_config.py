import json
import tempfile
import unittest
from pathlib import Path

from huelightperfmon.config import AppConfig, ConfigError, ConfigStore, app_data_directory


class AppConfigTests(unittest.TestCase):
    def test_ready_requires_all_connection_fields(self) -> None:
        self.assertFalse(AppConfig().is_ready)
        self.assertTrue(AppConfig(bridge_url="192.0.2.1", token="token", light_id="4").is_ready)

    def test_validation_rejects_reversed_ranges(self) -> None:
        with self.assertRaisesRegex(ConfigError, "Sensor maximum"):
            AppConfig(sensor_min=100, sensor_max=10).validate()
        with self.assertRaisesRegex(ConfigError, "Maximum brightness"):
            AppConfig(brightness_min=80, brightness_max=20).validate()

    def test_unknown_future_fields_are_ignored(self) -> None:
        config = AppConfig.from_dict({"sensor": "cpu_total", "future_option": True})
        self.assertEqual(config.sensor, "cpu_total")

    def test_existing_settings_gain_disabled_startup_default(self) -> None:
        config = AppConfig.from_dict(
            {
                "bridge_url": "http://bridge",
                "token": "saved-token",
                "light_id": "9",
                "brightness_min": 35,
                "enabled": False,
            }
        )
        self.assertEqual(config.bridge_url, "http://bridge")
        self.assertEqual(config.token, "saved-token")
        self.assertEqual(config.light_id, "9")
        self.assertEqual(config.brightness_min, 35)
        self.assertFalse(config.enabled)
        self.assertFalse(config.start_with_windows)

    def test_appdata_location(self) -> None:
        path = app_data_directory({"APPDATA": "C:/Users/test/AppData/Roaming"})
        self.assertEqual(path.as_posix(), "C:/Users/test/AppData/Roaming/HueLightPerfMon")


class ConfigStoreTests(unittest.TestCase):
    def test_resaving_older_file_preserves_existing_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            existing = {
                "bridge_url": "http://saved-bridge",
                "token": "saved-token",
                "light_id": "12",
                "sensor": "cpu_total",
                "brightness_min": 42,
                "enabled": False,
            }
            path.write_text(json.dumps(existing), encoding="utf-8")
            store = ConfigStore(path)

            store.save(store.load())

            saved = json.loads(path.read_text(encoding="utf-8"))
            for key, value in existing.items():
                self.assertEqual(saved[key], value)
            self.assertFalse(saved["start_with_windows"])

    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ConfigStore(path)
            expected = AppConfig(bridge_url="http://bridge", token="secret", light_id="7")
            store.save(expected)
            self.assertEqual(store.load(), expected)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["token"], "secret")

    def test_malformed_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("not json", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "Could not read"):
                ConfigStore(path).load()


if __name__ == "__main__":
    unittest.main()
