from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_VERSION_FILE = ROOT / "app_version.py"
INSTALLER_FILE = ROOT / "installer.nsi"


def parse_version(version: str) -> tuple[int, int, int]:
    parts = version.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("Version must be in the form major.minor.patch")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def read_current_version() -> tuple[int, int, int]:
    text = APP_VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"', text)
    if not match:
        raise RuntimeError("Could not find APP_VERSION in app_version.py")
    return parse_version(match.group(1))


def bump_version(current: tuple[int, int, int], bump_type: str) -> tuple[int, int, int]:
    major, minor, patch = current
    if bump_type == "major":
        return major + 1, 0, 0
    if bump_type == "minor":
        return major, minor + 1, 0
    if bump_type == "patch":
        return major, minor, patch + 1
    raise ValueError(f"Unsupported bump type: {bump_type}")


def write_app_version(version: tuple[int, int, int]):
    version_str = ".".join(str(part) for part in version)
    APP_VERSION_FILE.write_text(
        f'APP_VERSION = "{version_str}"\n\n\n'
        "def get_version_parts() -> tuple[int, int, int]:\n"
        '    major, minor, patch = APP_VERSION.split(".")\n'
        "    return int(major), int(minor), int(patch)\n",
        encoding="utf-8",
    )


def write_installer_version(version: tuple[int, int, int]):
    major, minor, patch = version
    text = INSTALLER_FILE.read_text(encoding="utf-8")
    text = re.sub(r"!define VERSIONMAJOR \d+", f"!define VERSIONMAJOR {major}", text)
    text = re.sub(r"!define VERSIONMINOR \d+", f"!define VERSIONMINOR {minor}", text)
    text = re.sub(r"!define VERSIONBUILD \d+", f"!define VERSIONBUILD {patch}", text)
    INSTALLER_FILE.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Bump application version.")
    parser.add_argument("--bump", choices=["major", "minor", "patch"], help="Semantic version part to bump.")
    parser.add_argument("--set-version", help="Explicit version to set, e.g. 1.2.3")
    args = parser.parse_args()

    if not args.bump and not args.set_version:
        raise SystemExit("Provide either --bump or --set-version.")
    if args.bump and args.set_version:
        raise SystemExit("Use either --bump or --set-version, not both.")

    current = read_current_version()
    target = parse_version(args.set_version) if args.set_version else bump_version(current, args.bump)

    write_app_version(target)
    write_installer_version(target)
    print(".".join(str(part) for part in target))


if __name__ == "__main__":
    main()
