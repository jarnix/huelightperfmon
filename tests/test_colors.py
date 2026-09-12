import unittest

from huelightperfmon.colors import map_sensor_to_hue, sensor_fraction


class SensorFractionTests(unittest.TestCase):
    def test_clamps_below_and_above_range(self) -> None:
        self.assertEqual(sensor_fraction(-1, 0, 100), 0)
        self.assertEqual(sensor_fraction(101, 0, 100), 1)

    def test_rejects_empty_range(self) -> None:
        with self.assertRaises(ValueError):
            sensor_fraction(5, 10, 10)


class HueMappingTests(unittest.TestCase):
    def test_maps_range_endpoints(self) -> None:
        low = map_sensor_to_hue(0, 0, 100, "#00ff00", "#ff0000", 20, 100)
        high = map_sensor_to_hue(100, 0, 100, "#00ff00", "#ff0000", 20, 100)

        self.assertAlmostEqual(low.hue, 65535 / 3, delta=1)
        self.assertEqual(low.saturation, 254)
        self.assertEqual(low.brightness, 51)
        self.assertIn(high.hue, (0, 65535))
        self.assertEqual(high.brightness, 254)

    def test_green_to_red_midpoint_is_yellow(self) -> None:
        midpoint = map_sensor_to_hue(50, 0, 100, "#00ff00", "#ff0000", 20, 100)
        self.assertAlmostEqual(midpoint.hue, 65535 / 6, delta=1)


if __name__ == "__main__":
    unittest.main()

