"""Publish primitive legacy map audit records without initializing the solver."""

import json
import os
from pathlib import Path


def write(path, receipt):
    """Serialize the existing schema and publish a complete, exclusive file."""
    parent = path.parent.resolve(strict=True)
    if parent.is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("A map receipt needs a writable local publication directory")
    data = (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)+"\n").encode("utf-8")
    temporary = parent/f".{path.name}.{os.urandom(8).hex()}"
    stream = temporary.open("xb")
    try:
        with stream:
            stream.write(data)
        os.link(temporary, parent/path.name)
    finally:
        temporary.unlink()
