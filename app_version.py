APP_VERSION = "1.1.2"


def get_version_parts() -> tuple[int, int, int]:
    major, minor, patch = APP_VERSION.split(".")
    return int(major), int(minor), int(patch)
