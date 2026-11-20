import os
import subprocess

import pytest

from tools.pipeline_eval.qualification import portable_verifier_run as run


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    scratch = tmp_path_factory.mktemp("portable-verifier")
    binary = scratch / "verifier"
    command = run.command("x86")
    flags = [part for part in command if part not in ("-march=x86-64-v3", "-fstack-usage")]
    subprocess.run(
        [*flags, "-o", binary],
        check=True,
        cwd=scratch,
        env=os.environ | {"TMPDIR": str(scratch)},
    )
    return binary


def test_portable_flat_iq_unbracketed_peak_and_exact_ties(executable):
    subprocess.run([executable, "--self-test"], check=True)


def test_portable_command_rejects_truncated_raw_input(executable, tmp_path):
    raw = tmp_path / "bad.bin"
    raw.write_bytes(b"LEOVRF01\x01\x00\x00\x00")
    result = subprocess.run([executable, raw], capture_output=True)
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"truncated authenticated verifier fixture" in result.stderr
