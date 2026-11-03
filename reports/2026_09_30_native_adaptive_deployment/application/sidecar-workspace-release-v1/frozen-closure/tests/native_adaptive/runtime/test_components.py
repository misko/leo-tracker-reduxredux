"""Compile and exercise portable runtime/policy components without radio access."""

import hashlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "component,binaries",
    [
        ("runtime", ("test-runtime",)),
        ("policy", ("test-original_policy", "test-continuous")),
        ("device", ("test-caps",)),
    ],
)
def test_native_components(tmp_path, component, binaries):
    subprocess.run(
        ["bash", str(ROOT / "native/adaptive" / component / "build.sh"), str(tmp_path)],
        check=True,
        timeout=60,
    )
    for binary in binaries:
        result = subprocess.run(
            [str(tmp_path / binary)], check=True, capture_output=True, text=True, timeout=30
        )
        assert "pass" in result.stdout.lower()
    if component == "runtime":
        iq = tmp_path / "window.ci16"
        payload = bytes(range(256)) * 3 + bytes(range(192))
        assert len(payload) == 120 * 8
        iq.write_bytes(payload)
        args = [
            str(tmp_path / "leo-windows"),
            str(iq),
            "1000",
            "2",
            "9007199254740993",
            "9007199254741113",
            "3",
            "7",
        ]
        output = subprocess.run(args, check=True, capture_output=True, text=True).stdout
        assert (
            output == "0\t9007199254740993\t20\t" + hashlib.sha256(payload[:160]).hexdigest() + "\n"
        )
        for invalid in (payload[:-1], payload + b"x"):
            iq.write_bytes(invalid)
            assert subprocess.run(args, capture_output=True).returncode == 2
