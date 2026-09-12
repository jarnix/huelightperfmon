from __future__ import annotations

from pathlib import Path

from huelightperfmon.app import _create_tray_image


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    output = project_root / "assets" / "huelightperfmon.ico"
    output.parent.mkdir(parents=True, exist_ok=True)
    image = _create_tray_image(256)
    image.save(output, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Created {output}")


if __name__ == "__main__":
    main()

