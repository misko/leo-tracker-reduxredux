import json
from pathlib import Path
from sys import path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from reports.ALGO08.v3 import legacy_first_map_input as first
from leo.contracts.digests import sha256_digest
from leo.storage.errors import BundleCorruptionError


def command_module():
    here = Path(first.__file__).parent
    with patch("sys.path", [str(here), *path]):
        from reports.ALGO08.v3 import legacy_first_map_panel
    return legacy_first_map_panel


def test_original_command_cannot_consume_a_prior_plan(tmp_path):
    panel = command_module()
    flags = ["--recording", "old-recording", "--archive", "old-archive", "--region", "old-offer",
             "--archive-sha256", "old-pin", "--output", "old-output", "--legacy-first-map-plan",
             "prior-custody", "--legacy-first-map-plan-sha256", "prior-pin", "--history-risk-route",
             "--cairo-residual-layout", "--legacy-first-map-history", "history.so",
             "--legacy-first-map-replay", "replay.so"]
    command = ["timeout", "--kill-after=2s", "75s", "python", "-IB", panel.ENTRY, *flags]
    scoped = [value.replace("old-", "new-") for value in flags[:8]]
    output = tmp_path / "output"
    updated = panel.command_for(command, scoped, output)
    assert updated[6:14] == scoped
    assert updated[15] == str(output)
    assert updated[16:] == flags[14:]
    assert "prior-custody" in command
    with pytest.raises(ValueError, match="original input"):
        panel.command_for([*command, "--legacy-map-custody", "an-existing-map"], scoped, output)


def test_independent_readback_allows_exception_payloads_above_custody_limit():
    with TemporaryDirectory(dir="/dev/shm") as root:
        verify_exception_readback(Path(root))


def verify_exception_readback(tmp_path):
    panel = command_module()
    original = tmp_path / "independent"
    current = tmp_path / "legacy-first-maps"
    payload = bytes(300_000)
    row = dict(map="member-000000.json", map_kind="exception", map_sha256=sha256_digest(payload), encoded=100)
    body = json.dumps(dict(session="session", inventory="inventory", windows=1,
                           raw_authority="authority", members=[row])).encode()
    pin = sha256_digest(body)
    for folder in (original, current):
        folder.mkdir()
        (folder / "custody.json").write_bytes(body)
        (folder / row["map"]).write_bytes(payload)
    audit = dict(authority_mode="verified-first-use", plan_sha256=pin, finished_raw_authority="authority",
                 members=[dict(row, map_bytes=len(payload), proof=dict(prefix_bytes=640_000, original_encoded_reused=100))])
    (tmp_path / "legacy-first-map-acquisition.json").write_text(json.dumps(audit))
    req = dict(session="session", inventory="inventory", authority="authority")
    assert panel.map_parity(tmp_path, original, pin, req, 1, {"exception": 1}) == audit
    (current / row["map"]).write_bytes(payload[:-1])
    with pytest.raises(BundleCorruptionError):
        panel.map_parity(tmp_path, original, pin, req, 1, {"exception": 1})
