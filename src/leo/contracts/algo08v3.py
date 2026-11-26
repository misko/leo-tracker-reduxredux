"""Release identity emitted by the frozen Gauss ALGO08v3 launcher."""

VERSION = "ALGO08v3"
EXECUTION_RELEASE = {
    "version": VERSION,
    "frozen_specification": "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f",
    "detector_sha256": "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5",
}


def validate_release(value):
    if value != EXECUTION_RELEASE:
        raise ValueError("Unrecognized ALGO08v3 execution release")
