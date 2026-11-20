import gzip
import io
import shlex
import subprocess
import tarfile

import pytest

from tools.pipeline_eval.qualification import capture_board_replay as replay


def test_short_packet_reuses_the_arm_elf_and_exact_iq_payload():
    payload, receipt = replay.packet()
    assert len(payload) < replay.MAX_STREAM_BYTES
    assert replay.sha(payload) == receipt["archive_sha256"]
    with (
        tarfile.open(fileobj=io.BytesIO(payload)) as capsule,
        tarfile.open(replay.ARCHIVE) as source,
    ):
        assert capsule.getnames() == ["capture-board-folded", "folded.input"]
        assert replay.sha(capsule.extractfile("capture-board-folded").read()) == replay.BINARY_SHA
        short = capsule.extractfile("folded.input").read()
        full = source.extractfile("folded.input").read()
    assert replay.HEADER.unpack_from(short) == (*replay.FULL[:-2], 512, replay.FULL[-1])
    assert short[replay.HEADER.size :] == full[replay.HEADER.size :]
    assert replay.sha(short) == receipt["input_sha256"]
    assert receipt["cells"] == 10_752


def test_replay_rejects_unbound_inputs(tmp_path):
    altered = tmp_path / "unexpected.tar.gz"
    altered.write_bytes(b"unsealed")
    with pytest.raises(ValueError, match="source capsule SHA-256"):
        replay.packet(altered)
    with pytest.raises(ValueError, match="authenticated capture-era fixture"):
        replay.shorten(b"unsealed")
    with pytest.raises(ValueError, match="exact local capsule"):
        replay.command("replay", archive_sha="a" * 64, fixture_sha="g" * 64)


def test_replay_verifies_exact_stream_across_gzip_encodings():
    plain, fields = replay.plain_packet()
    archive = gzip.compress(plain, compresslevel=5, mtime=1)
    receipt = dict(fields, archive_sha256=replay.sha(archive), archive_bytes=len(archive))
    replay.verify(archive, receipt)
    changed = gzip.compress(b"incorrect members", mtime=1)
    with pytest.raises(ValueError, match="members differ"):
        replay.verify(
            changed, dict(receipt, archive_sha256=replay.sha(changed), archive_bytes=len(changed))
        )


def test_remote_command_is_single_shell_and_refuses_wrong_architecture(tmp_path):
    argv = shlex.split(replay.command("replay", archive_sha="a" * 64, fixture_sha="b" * 64))
    assert argv[:2] == ["sh", "-c"]
    assert argv[3:] == ["capture-board-replay", "replay", "a" * 64, "b" * 64]
    subprocess.run(["sh", "-n", replay.SHELL], check=True)
    uname = tmp_path / "uname"
    uname.write_text("#!/bin/sh\nprintf 'x86_64\\n'\n")
    uname.chmod(0o700)
    result = subprocess.run(
        ["/bin/sh", *argv[1:]], env={"PATH": str(tmp_path)}, capture_output=True
    )
    assert result.returncode == 1
    assert b"Expected the ARMv7 development board" in result.stderr
