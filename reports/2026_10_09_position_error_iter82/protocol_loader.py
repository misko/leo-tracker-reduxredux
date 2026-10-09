"""Verify the historical DS17 protocol without ambiguous top-level imports."""

import hashlib
import json


def verified_protocol(directory):
    payload = (directory / "protocol.json").read_bytes()
    actual = "sha256:" + hashlib.sha256(payload).hexdigest()
    assert actual == (directory / "protocol.sha256").read_text().strip()
    return json.loads(payload)
