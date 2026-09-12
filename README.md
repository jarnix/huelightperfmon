# Hue Light Performance Monitor

A small Windows tray application that drives the color and brightness of one Philips Hue light from a local performance sensor. The first sensor is total CPU load; the sensor registry is intentionally small and extensible.

The app uses the Hue bridge's basic REST API (the `/api/<token>/lights/...` v1 endpoints). It talks directly to the bridge on your local network and does not require a cloud account.

## What the first version does

- Lives in the Windows notification area with Settings, Start, Stop, and Exit commands.
- Finds Hue bridges on the LAN using mDNS, with the official Hue discovery service as a fallback.
- Pairs through an in-app link-button dialog and saves the generated token—no manual REST request required.
- Reads total CPU usage without blocking the UI.
- Maps a configurable sensor range to a two-color HSV gradient.
- Maps that same range to configurable minimum and maximum brightness.
- Lets you query the bridge and select one of its lights.
- Includes a **Test now** action before saving.
- Saves configuration atomically to `%APPDATA%\HueLightPerfMon\config.json`.
- Writes runtime errors to `%LOCALAPPDATA%\HueLightPerfMon\huelightperfmon.log`.
- Builds as a single windowless Windows `.exe` with PyInstaller.

Stopping monitoring leaves the light at its last color and intensity. It does not switch the light off.

## Hue setup

The app can discover and pair with the bridge for you:

1. Start the app and choose **Find bridges**. You can instead type the bridge IP manually, for example `192.168.1.20`.
2. Select the bridge and choose **Pair bridge**.
3. When prompted, press the large physical link button on top of the bridge. The app retries for 30 seconds and fills in the generated token automatically.
4. The light list loads automatically; select the light you want to control and save.

Bridge search first uses local mDNS (`_hue._tcp.local.`). If multicast discovery finds nothing, it tries `discovery.meethue.com`. Windows Firewall may ask for permission for local-network discovery. Manual IP entry always remains available.

Use the base bridge address only, not an address ending in `/api`. A bare IP address defaults to HTTPS, as required by current Hue firmware. You can explicitly enter `http://<bridge-ip>` only for a legacy bridge that still supports it.

Hue bridges can use certificates issued by Hue's private certificate authority. **Verify bridge TLS certificate** is therefore off by default for compatibility; the connection is encrypted but the bridge identity is not authenticated. Enable strict verification only if your computer trusts the bridge certificate. Keep the PC and bridge on a trusted local network.

The token is stored as readable JSON in your Windows user profile. Do not share the config file.

## Run from source

Python 3.10 or newer is required. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\pythonw.exe -m huelightperfmon
```

On first launch, the Settings window opens automatically. On later launches, use the tray icon's menu.

## Build the Windows executable

Run:

```powershell
.\build.ps1
```

The script creates the virtual environment if necessary, installs the runtime and build dependencies, generates the multi-resolution app icon, and writes:

```text
dist\HueLightPerfMon.exe
```

The executable is portable, but its configuration remains per-user in `%APPDATA%`.

## Configuration fields

| Field | Meaning |
| --- | --- |
| Bridge URL or IP | Local Hue bridge base address |
| Application token | Hue v1 API username/token, normally created by **Pair bridge** |
| Hue light | The single light controlled by the app |
| Verify bridge TLS certificate | Strict certificate validation when your system trusts the Hue bridge CA |
| Sensor range | Values clamped to the low and high ends of the mapping |
| Low/high color | Gradient endpoints in `#RRGGBB` form |
| Brightness | Intensity at the low and high sensor values |
| Update interval | Time between sensor readings and Hue commands |
| Hue transition | Transition duration sent to the bridge |

The default mapping is 0–100% CPU, green–red, and 20–100% brightness, updated every two seconds.

## Development checks

Core behavior has no GUI dependency and can be tested with the standard library test runner after installing the package:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The main extension points are:

- `sensors.py`: register another sensor with a key, display label, unit, and reader function.
- `colors.py`: adjust how normalized sensor values become Hue v1 state values.
- `controller.py`: sampling, error handling, and bridge update cadence.
