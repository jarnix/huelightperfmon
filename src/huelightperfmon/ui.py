from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import colorchooser, ttk
from typing import Callable

from huelightperfmon.colors import map_sensor_to_hue
from huelightperfmon.config import AppConfig, ConfigError, ConfigStore
from huelightperfmon.discovery import DiscoveredBridge, discover_bridges
from huelightperfmon.hue import (
    HueApiClient,
    HueLight,
    HueLinkButtonRequired,
    HuePairingClient,
    normalize_bridge_url,
)
from huelightperfmon.sensors import SensorRegistry


class ConfigurationWindow:
    def __init__(
        self,
        root: tk.Tk,
        config: AppConfig,
        store: ConfigStore,
        sensors: SensorRegistry,
        apply_config: Callable[[AppConfig], None],
        schedule_ui: Callable[[Callable[[], None]], None],
        closed: Callable[[], None],
    ) -> None:
        self._store = store
        self._sensors = sensors
        self._apply_config = apply_config
        self._schedule_ui = schedule_ui
        self._closed_callback = closed
        self._bridge_addresses: dict[str, str] = {}
        self._light_ids: dict[str, str] = {}
        self._pairing_dialog: PairingDialog | None = None
        self._sensor_keys = {sensor.label: sensor.key for sensor in sensors.all()}
        sensor_definitions = sensors.all()
        try:
            selected_sensor = sensors.get(config.sensor).label
        except KeyError:
            selected_sensor = sensor_definitions[0].label

        self.window = tk.Toplevel(root)
        self.window.title("Hue Light Performance Monitor")
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self._close)

        self.bridge_url = tk.StringVar(value=config.bridge_url)
        self.token = tk.StringVar(value=config.token)
        self.light = tk.StringVar(value=config.light_id)
        self.verify_tls = tk.BooleanVar(value=config.verify_tls)
        self.sensor = tk.StringVar(value=selected_sensor)
        self.sensor_min = tk.StringVar(value=f"{config.sensor_min:g}")
        self.sensor_max = tk.StringVar(value=f"{config.sensor_max:g}")
        self.low_color = tk.StringVar(value=config.low_color)
        self.high_color = tk.StringVar(value=config.high_color)
        self.brightness_min = tk.StringVar(value=str(config.brightness_min))
        self.brightness_max = tk.StringVar(value=str(config.brightness_max))
        self.update_seconds = tk.StringVar(value=f"{config.update_seconds:g}")
        self.transition_seconds = tk.StringVar(value=f"{config.transition_seconds:g}")
        self.enabled = tk.BooleanVar(value=config.enabled)
        self.status = tk.StringVar(value="Enter the bridge details, then load the light list.")

        outer = ttk.Frame(self.window, padding=12)
        outer.grid(sticky="nsew")
        self._build_bridge_section(outer)
        self._build_mapping_section(outer)
        self._build_timing_section(outer)

        ttk.Label(outer, textvariable=self.status, foreground="#444444", wraplength=540).grid(
            row=3, column=0, sticky="ew", pady=(10, 6)
        )
        buttons = ttk.Frame(outer)
        buttons.grid(row=4, column=0, sticky="e")
        self.test_button = ttk.Button(buttons, text="Test now", command=self._test)
        self.test_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Cancel", command=self._close).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="Save", command=self._save).grid(row=0, column=2)

        self.window.update_idletasks()
        self.window.grab_set()
        self.window.focus_force()

    def _build_bridge_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Hue bridge", padding=10)
        frame.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Bridge URL or IP").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        self.bridge_combo = ttk.Combobox(frame, textvariable=self.bridge_url, width=42)
        self.bridge_combo.grid(row=0, column=1, sticky="ew", pady=3)
        self.find_button = ttk.Button(frame, text="Find bridges", command=self._find_bridges)
        self.find_button.grid(row=0, column=2, padx=(8, 0), pady=3)
        ttk.Label(frame, text="Application token").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Entry(frame, textvariable=self.token, show="•", width=42).grid(row=1, column=1, sticky="ew", pady=3)
        self.pair_button = ttk.Button(frame, text="Pair bridge", command=self._pair_bridge)
        self.pair_button.grid(row=1, column=2, padx=(8, 0), pady=3)
        ttk.Label(frame, text="Hue light").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=3)
        self.light_combo = ttk.Combobox(frame, textvariable=self.light, width=42)
        self.light_combo.grid(row=2, column=1, sticky="ew", pady=3)
        self.load_button = ttk.Button(frame, text="Load lights", command=self._load_lights)
        self.load_button.grid(row=2, column=2, padx=(8, 0), pady=3)
        ttk.Checkbutton(
            frame,
            text="Verify bridge TLS certificate (strict)",
            variable=self.verify_tls,
        ).grid(row=3, column=1, columnspan=2, sticky="w", pady=(3, 0))

    def _build_mapping_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Sensor mapping", padding=10)
        frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        ttk.Label(frame, text="Sensor").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Combobox(
            frame,
            textvariable=self.sensor,
            values=tuple(self._sensor_keys),
            state="readonly",
            width=24,
        ).grid(row=0, column=1, columnspan=2, sticky="w", pady=3)

        ttk.Label(frame, text="Sensor range").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Entry(frame, textvariable=self.sensor_min, width=10).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(frame, text="to").grid(row=1, column=2, padx=5)
        ttk.Entry(frame, textvariable=self.sensor_max, width=10).grid(row=1, column=3, sticky="w", pady=3)

        self._color_row(frame, 2, "Low color", self.low_color)
        self._color_row(frame, 3, "High color", self.high_color)

        ttk.Label(frame, text="Brightness (%)").grid(row=4, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Entry(frame, textvariable=self.brightness_min, width=10).grid(row=4, column=1, sticky="w", pady=3)
        ttk.Label(frame, text="to").grid(row=4, column=2, padx=5)
        ttk.Entry(frame, textvariable=self.brightness_max, width=10).grid(row=4, column=3, sticky="w", pady=3)

    def _build_timing_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Behavior", padding=10)
        frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(frame, text="Update every (seconds)").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Entry(frame, textvariable=self.update_seconds, width=10).grid(row=0, column=1, sticky="w", pady=3)
        ttk.Label(frame, text="Hue transition (seconds)").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Entry(frame, textvariable=self.transition_seconds, width=10).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Checkbutton(frame, text="Run monitoring after saving", variable=self.enabled).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(5, 0)
        )

    def _color_row(self, frame: ttk.LabelFrame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Entry(frame, textvariable=variable, width=10).grid(row=row, column=1, sticky="w", pady=3)
        preview = tk.Label(frame, width=3, relief="sunken", background=variable.get())
        preview.grid(row=row, column=2, padx=5)

        def choose() -> None:
            selected = colorchooser.askcolor(variable.get(), parent=self.window)[1]
            if selected:
                variable.set(selected.lower())
                preview.configure(background=selected)

        ttk.Button(frame, text="Choose…", command=choose).grid(row=row, column=3, sticky="w", pady=3)

    def _make_config(self, *, require_connection: bool) -> AppConfig:
        light_value = self.light.get().strip()
        config = AppConfig(
            bridge_url=self._current_bridge_url(),
            token=self.token.get().strip(),
            light_id=self._light_ids.get(light_value, light_value),
            verify_tls=self.verify_tls.get(),
            sensor=self._sensor_keys[self.sensor.get()],
            sensor_min=float(self.sensor_min.get()),
            sensor_max=float(self.sensor_max.get()),
            low_color=self.low_color.get().strip().lower(),
            high_color=self.high_color.get().strip().lower(),
            brightness_min=int(self.brightness_min.get()),
            brightness_max=int(self.brightness_max.get()),
            update_seconds=float(self.update_seconds.get()),
            transition_seconds=float(self.transition_seconds.get()),
            enabled=self.enabled.get(),
        )
        config.validate(require_connection=require_connection)
        return config

    def _current_bridge_url(self) -> str:
        value = self.bridge_url.get().strip()
        return self._bridge_addresses.get(value, value)

    def _find_bridges(self) -> None:
        self.find_button.configure(state="disabled")
        self.status.set("Searching the local network for Hue bridges…")

        def worker() -> None:
            try:
                bridges = discover_bridges()
            except Exception as exc:
                self._schedule_ui(lambda message=str(exc): self._discovery_failed(message))
                return
            self._schedule_ui(lambda: self._bridges_found(bridges))

        threading.Thread(target=worker, name="discover-hue-bridges", daemon=True).start()

    def _bridges_found(self, bridges: list[DiscoveredBridge]) -> None:
        if not self.window.winfo_exists():
            return
        self.find_button.configure(state="normal")
        if not bridges:
            self.status.set(
                "No Hue bridge was found. Check that this PC is on the same network, or enter the bridge IP manually."
            )
            return

        current = self._current_bridge_url()
        try:
            normalized_current = normalize_bridge_url(current) if current else ""
        except Exception:
            normalized_current = current
        displays = [bridge.display_name for bridge in bridges]
        self._bridge_addresses = {bridge.display_name: bridge.url for bridge in bridges}
        self.bridge_combo.configure(values=displays)
        selected = next(
            (
                bridge.display_name
                for bridge in bridges
                if bridge.url.rstrip("/") == normalized_current.rstrip("/")
            ),
            displays[0],
        )
        self.bridge_url.set(selected)
        if len(bridges) == 1:
            self.status.set("Found one Hue bridge. Press Pair bridge and then press its physical link button.")
        else:
            self.status.set(f"Found {len(bridges)} Hue bridges. Select one, then press Pair bridge.")

    def _discovery_failed(self, message: str) -> None:
        if not self.window.winfo_exists():
            return
        self.find_button.configure(state="normal")
        self.status.set(f"Bridge search failed: {message} You can still enter the IP manually.")

    def _pair_bridge(self) -> None:
        bridge_url = self._current_bridge_url()
        if not bridge_url:
            self.status.set("Find a bridge or enter its IP address before pairing.")
            return
        if self._pairing_dialog and self._pairing_dialog.window.winfo_exists():
            self._pairing_dialog.window.lift()
            return
        self.pair_button.configure(state="disabled")
        self._pairing_dialog = PairingDialog(
            self.window,
            bridge_url,
            self.verify_tls.get(),
            self._schedule_ui,
            self._paired,
            self._pairing_closed,
        )

    def _paired(self, token: str) -> None:
        if not self.window.winfo_exists():
            return
        self.token.set(token)
        self.status.set("Pairing succeeded. Loading the bridge's lights…")
        self._load_lights()

    def _pairing_closed(self) -> None:
        self._pairing_dialog = None
        if self.window.winfo_exists():
            self.pair_button.configure(state="normal")

    def _load_lights(self) -> None:
        bridge_url = self._current_bridge_url()
        token = self.token.get().strip()
        verify_tls = self.verify_tls.get()
        if not bridge_url or not token:
            self.status.set("Enter the bridge URL and application token first.")
            return
        self.load_button.configure(state="disabled")
        self.status.set("Contacting Hue bridge…")

        def worker() -> None:
            try:
                lights = HueApiClient(bridge_url, token, verify_tls=verify_tls).get_lights()
            except Exception as exc:
                self._schedule_ui(lambda message=str(exc): self._lights_failed(message))
                return
            self._schedule_ui(lambda: self._lights_loaded(lights))

        threading.Thread(target=worker, name="load-hue-lights", daemon=True).start()

    def _lights_loaded(self, lights: list[HueLight]) -> None:
        if not self.window.winfo_exists():
            return
        self.load_button.configure(state="normal")
        current_id = self._light_ids.get(self.light.get(), self.light.get())
        displays = [f"{light.name}  [id {light.id}]" for light in lights]
        self._light_ids = {display: light.id for display, light in zip(displays, lights)}
        self.light_combo.configure(values=displays, state="readonly")
        selected = next((display for display, light_id in self._light_ids.items() if light_id == current_id), "")
        if selected:
            self.light.set(selected)
        elif displays:
            self.light.set(displays[0])
        self.status.set(f"Loaded {len(lights)} Hue light(s)." if lights else "The bridge reported no lights.")

    def _lights_failed(self, message: str) -> None:
        if not self.window.winfo_exists():
            return
        self.load_button.configure(state="normal")
        self.status.set(message)

    def _test(self) -> None:
        try:
            config = self._make_config(require_connection=True)
        except (ConfigError, ValueError, KeyError) as exc:
            self.status.set(str(exc))
            return
        self.test_button.configure(state="disabled")
        self.status.set("Reading sensor and testing light…")

        def worker() -> None:
            try:
                sensor = self._sensors.get(config.sensor)
                value = sensor.reader()
                target = map_sensor_to_hue(
                    value,
                    config.sensor_min,
                    config.sensor_max,
                    config.low_color,
                    config.high_color,
                    config.brightness_min,
                    config.brightness_max,
                )
                HueApiClient(
                    config.bridge_url,
                    config.token,
                    verify_tls=config.verify_tls,
                ).set_light_state(
                    config.light_id,
                    hue=target.hue,
                    saturation=target.saturation,
                    brightness=target.brightness,
                    transition_seconds=config.transition_seconds,
                )
            except Exception as exc:
                self._schedule_ui(lambda message=str(exc): self._test_finished(message))
                return
            self._schedule_ui(
                lambda: self._test_finished(f"Success: {sensor.label} is {value:.1f}{sensor.unit}.")
            )

        threading.Thread(target=worker, name="test-hue-light", daemon=True).start()

    def _test_finished(self, message: str) -> None:
        if not self.window.winfo_exists():
            return
        self.test_button.configure(state="normal")
        self.status.set(message)

    def _save(self) -> None:
        try:
            config = self._make_config(require_connection=True)
            self._store.save(config)
        except (ConfigError, ValueError, KeyError) as exc:
            self.status.set(str(exc))
            return
        self._apply_config(config)
        self._close()

    def _close(self) -> None:
        if self._pairing_dialog:
            self._pairing_dialog.close()
            self._pairing_dialog = None
        if self.window.winfo_exists():
            self.window.grab_release()
            self.window.destroy()
        self._closed_callback()


class PairingDialog:
    PAIRING_WINDOW_SECONDS = 30
    RETRY_INTERVAL_SECONDS = 1.5

    def __init__(
        self,
        parent: tk.Toplevel,
        bridge_url: str,
        verify_tls: bool,
        schedule_ui: Callable[[Callable[[], None]], None],
        succeeded: Callable[[str], None],
        closed: Callable[[], None],
    ) -> None:
        self._bridge_url = bridge_url
        self._verify_tls = verify_tls
        self._schedule_ui = schedule_ui
        self._succeeded_callback = succeeded
        self._closed_callback = closed
        self._cancel_event = threading.Event()
        self._closed = False

        self.window = tk.Toplevel(parent)
        self.window.title("Pair Hue bridge")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        frame = ttk.Frame(self.window, padding=18)
        frame.grid(sticky="nsew")
        ttk.Label(
            frame,
            text="Press the large physical link button on your Hue bridge now.",
            font=("Segoe UI", 10, "bold"),
            wraplength=390,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            frame,
            text="The app will automatically retry until the bridge grants access. No manual API request is needed.",
            wraplength=390,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 12))
        self.status = tk.StringVar(value="Waiting for the bridge button…")
        ttk.Label(frame, textvariable=self.status, wraplength=390).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=270)
        self.progress.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        self.progress.start(12)
        self.retry_button = ttk.Button(frame, text="Try again", command=self._start, state="disabled")
        self.retry_button.grid(row=4, column=0, sticky="e", padx=(0, 8))
        ttk.Button(frame, text="Cancel", command=self.close).grid(row=4, column=1, sticky="e")

        self.window.grab_set()
        self.window.focus_force()
        self.window.after(100, self._start)

    def _start(self) -> None:
        self._cancel_event = threading.Event()
        self.retry_button.configure(state="disabled")
        self.progress.start(12)
        self.status.set("Waiting for the bridge button…")

        def worker() -> None:
            client = HuePairingClient(self._bridge_url, verify_tls=self._verify_tls)
            deadline = time.monotonic() + self.PAIRING_WINDOW_SECONDS
            while not self._cancel_event.is_set() and time.monotonic() < deadline:
                try:
                    token = client.create_application_token()
                except HueLinkButtonRequired:
                    remaining = max(1, int(deadline - time.monotonic()))
                    self._schedule_ui(lambda seconds=remaining: self._still_waiting(seconds))
                    self._cancel_event.wait(self.RETRY_INTERVAL_SECONDS)
                    continue
                except Exception as exc:
                    self._schedule_ui(lambda message=str(exc): self._failed(message))
                    return
                self._schedule_ui(lambda: self._succeeded(token))
                return
            if not self._cancel_event.is_set():
                self._schedule_ui(self._timed_out)

        threading.Thread(target=worker, name="pair-hue-bridge", daemon=True).start()

    def _still_waiting(self, seconds: int) -> None:
        if self._exists():
            self.status.set(f"Waiting for the physical button… {seconds} seconds remaining.")

    def _failed(self, message: str) -> None:
        if not self._exists():
            return
        self.progress.stop()
        self.status.set(f"Pairing failed: {message}")
        self.retry_button.configure(state="normal")

    def _timed_out(self) -> None:
        if not self._exists():
            return
        self.progress.stop()
        self.status.set("The pairing window expired. Press Try again, then press the bridge button.")
        self.retry_button.configure(state="normal")

    def _succeeded(self, token: str) -> None:
        if not self._exists():
            return
        self.close()
        self._succeeded_callback(token)

    def _exists(self) -> bool:
        return not self._closed and bool(self.window.winfo_exists())

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_event.set()
        if self.window.winfo_exists():
            self.progress.stop()
            self.window.grab_release()
            self.window.destroy()
        self._closed_callback()
