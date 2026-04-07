APP_VERSION = "1.0.0"


def get_version_parts() -> tuple[int, int, int]:
    major, minor, patch = APP_VERSION.split(".")
    return int(major), int(minor), int(patch)
