"""Prepare a sealed short board input and render a command for an approved SSH route."""

import argparse
import gzip
import hashlib
import io
import json
import shlex
import struct
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = (
    ROOT
    / "reports/2026_11_19_receiver_screening/detector-origins/embedded/cortex-a9-offline.tar.gz"
)
SHELL = Path(__file__).with_suffix(".sh")
ARCHIVE_SHA = "1179cdc10242dbefc683ea8f9a4d96b18bf9588e3aa3a38832480c4cbd212123"
BINARY_SHA = "7a53b4f8a0c14c1b78557702c72d7cfca16aa628b9d89cbe6c3ae0a0cd09de74"
FULL_INPUT_SHA = "294eac42047a9f9fbaeb8b7ba26202bb137496603527ab0b7954e71af209636a"
HEADER = struct.Struct("<8s6Id")
FULL = (b"LEOFOLD1", 200_000, 13_333, 21, 12, 15, 13_333, 10_000_000.0)
EPOCHS = 512
MAX_STREAM_BYTES = 4 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def shorten(fixture):
    if sha(fixture) != FULL_INPUT_SHA or HEADER.unpack_from(fixture) != FULL:
        raise ValueError("input differs from the authenticated capture-era fixture")
    return HEADER.pack(*FULL[:-2], EPOCHS, FULL[-1]) + fixture[HEADER.size :]


def plain_packet(original=ARCHIVE):
    raw = original.read_bytes()
    if sha(raw) != ARCHIVE_SHA:
        raise ValueError("source capsule SHA-256 mismatch")
    with tarfile.open(fileobj=io.BytesIO(raw)) as source:
        elf = source.extractfile("capture-board-folded").read()
        fixture = shorten(source.extractfile("folded.input").read())
    if sha(elf) != BINARY_SHA:
        raise ValueError("the Cortex-A9 executable changed")
    plain = io.BytesIO()
    with tarfile.open(fileobj=plain, mode="w", format=tarfile.USTAR_FORMAT) as target:
        for name, data in (("capture-board-folded", elf), ("folded.input", fixture)):
            field = tarfile.TarInfo(name)
            field.size = len(data)
            field.mode = 0o700 if name == "capture-board-folded" else 0o600
            target.addfile(field, io.BytesIO(data))
    return plain.getvalue(), dict(
        parent_capsule_sha256=ARCHIVE_SHA,
        executable_sha256=BINARY_SHA,
        full_input_sha256=FULL_INPUT_SHA,
        input_sha256=sha(fixture),
        cells=EPOCHS * FULL[3],
        epochs=EPOCHS,
        frame_offsets=FULL[5],
        anchors=FULL[4],
        cfo_bins=FULL[3],
    )


def packet(original=ARCHIVE):
    plain, receipt = plain_packet(original)
    capsule = gzip.compress(plain, compresslevel=1, mtime=0)
    if len(capsule) > MAX_STREAM_BYTES:
        raise ValueError("archive exceeds the board stream cap")
    return capsule, dict(receipt, archive_sha256=sha(capsule), archive_bytes=len(capsule))


def verify(capsule, receipt):
    plain, fields = plain_packet()
    if len(capsule) > MAX_STREAM_BYTES or receipt != dict(
        fields, archive_sha256=sha(capsule), archive_bytes=len(capsule)
    ):
        raise ValueError("receipt does not bind the exact local replay capsule")
    # Gzip bytes can differ across host zlib versions. Authenticate the actual
    # stream and require the same canonical uncompressed tar and each member.
    with gzip.GzipFile(fileobj=io.BytesIO(capsule)) as compressed:
        if compressed.read(len(plain) + 1) != plain:
            raise ValueError("capsule members differ from the authenticated packet")


def command(action, *, archive_sha="", fixture_sha=""):
    if action == "replay" and not all(
        len(value) == 64 and set(value) <= set("0123456789abcdef")
        for value in (archive_sha, fixture_sha)
    ):
        raise ValueError("the replay requires the exact local capsule and fixture SHA-256")
    return shlex.join(
        ("sh", "-c", SHELL.read_text(), "capture-board-replay", action, archive_sha, fixture_sha)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("prepare")
    build.add_argument("output", type=Path)
    actions.add_parser("preflight-command")
    replay = actions.add_parser("replay-command")
    replay.add_argument("receipt", type=Path)
    replay.add_argument("capsule", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        data, receipt = packet()
        with args.output.open("xb") as output:
            output.write(data)
        print(json.dumps(receipt, indent=2, sort_keys=True))
    elif args.action == "preflight-command":
        print(command("preflight"))
    else:
        receipt = json.loads(args.receipt.read_bytes())
        with args.capsule.open("rb") as capsule:
            verify(capsule.read(MAX_STREAM_BYTES + 1), receipt)
        print(
            command(
                "replay", archive_sha=receipt["archive_sha256"], fixture_sha=receipt["input_sha256"]
            )
        )


if __name__ == "__main__":
    main()
