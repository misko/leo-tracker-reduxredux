import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

import ci16_packing
import packed_combined_input as packed
import seekable_member as seek


@pytest.fixture(scope="module")
def binary(tmp_path_factory):
    path = tmp_path_factory.mktemp("codec") / "packing.so"
    subprocess.run(["cc", "-std=c11", "-O3", "-shared", "-fPIC", str(ci16_packing.SOURCE),
                    "-o", str(path)], check=True)
    return path


def setup_recording(tmp, binary, *, chunk_windows=1, mapped_chunk=0, strict=False):
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.short_window import ShortWindowReader, ShortWindowWriter

    target = dict(target_id="scope", edge="lower", channel=1, rf_center_hz=11_700_000_000, lnb_lo_hz=10_000_000_000)
    configuration = dict(sample_rate_hz=10_000_000, window_ms=20, targets=[target])
    writer = ShortWindowWriter(tmp, "source", configuration=configuration, radio={}, receiver_ids=(0, 1),
                               schema_version=2, chunk_windows=chunk_windows, compression_level=1)
    for sequence in range(2):
        values = np.resize(np.array([-2048, 2047, -99, 47, sequence], dtype="<i2"), (seek.SAMPLES, 2, 2))
        writer.append(sequence=sequence, target_id="scope", samples=values,
                      acquisition={"visit": sequence}, powers=({}, {}))
    source = writer.finish(stop_reason="component fixture")
    original = ShortWindowReader(source)
    container = tmp / "packed-member"
    member_pin = seek.create(original, mapped_chunk, container, codec=ci16_packing.Packing(binary),
                             prefix_samples=seek.EIGHT_MS_SAMPLES if strict else seek.PREFIX_SAMPLES)
    entry = dict(path=str(source), manifest_digest=original.manifest_sha256)
    map_doc = dict(schema=packed.STRICT_EIGHT_SCHEMA if strict else packed.SCHEMA,
                   codec_sha256=seek.digest(binary.read_bytes()), members=[dict(
        directory=container.name, manifest_sha256=original.manifest_sha256, chunk_index=mapped_chunk, seek_sha256=member_pin)])
    return SimpleNamespace(FastSegmentSource=FastSegmentSource), entry, container, map_doc


def config(tmp, binary, mapping):
    content = json.dumps(mapping).encode()
    path = tmp / "map.json"
    path.write_bytes(content)
    temp = tmp / "runtime"
    temp.mkdir()
    return (path, seek.digest(content), binary), temp


def seen(scanner, entry):
    return [(window.sequence, window.iq_sha256, window.samples.tobytes())
            for window in scanner.FastSegmentSource(entry).windows()]


def test_only_trusted_unambiguous_sibling_members():
    good = dict(directory="member", manifest_sha256="a"*64, chunk_index=0, seek_sha256="sha256:"+"b"*64)
    doc = dict(schema=packed.SCHEMA, codec_sha256="c"*64, members=[good])
    assert packed.member_map(json.dumps(doc))[1] == {("sha256:"+"a"*64, 0): ("member", "sha256:"+"b"*64)}
    for rows in ([good, good], [dict(good, directory="..")], [dict(good, directory="../../outside")],
                 [dict(good, directory="/absolute")], [dict(good, seek_sha256="a0")], [dict(good, chunk_index=True)]):
        with pytest.raises(ValueError):
            packed.member_map(json.dumps(dict(doc, members=rows)))
    with pytest.raises(ValueError, match="together"):
        packed.request(SimpleNamespace(packed_ci16_map=Path("map.json")))


def test_mixed_original_and_packed_preserves_full_stream(tmp_path, binary):
    scan, entry, _, mapping = setup_recording(tmp_path, binary, mapped_chunk=1)
    expected = seen(scan, entry)
    request, temp = config(tmp_path, binary, mapping)
    audit = {}
    with packed.packed_source(scan, request, temp, audit):
        assert seen(scan, entry) == expected
    assert audit["fallback"] is None and audit["original_windows"] == 1
    row, = audit["members"]
    assert row["state"] == "packed" and row["checks"]["decoded_bytes"] == seek.WINDOW_BYTES
    assert row["encoded_blocks"] == 2 and row["checks"]["full_checks"] == 1


def test_corrupt_packed_tail_falls_back_before_delivery(tmp_path, binary):
    scan, entry, container, mapping = setup_recording(tmp_path, binary)
    expected = seen(scan, entry)
    tail = container / "tail.ci16p"
    tail.chmod(0o600)
    with tail.open("r+b") as output:
        output.seek(-1, 2)
        final = output.read(1)[0]
        output.seek(-1, 2)
        output.write(bytes([final ^ 128]))
    request, temp = config(tmp_path, binary, mapping)
    audit = {}
    with packed.packed_source(scan, request, temp, audit):
        assert seen(scan, entry) == expected
    assert audit["original_windows"] == 2
    row, = audit["members"]
    assert row["state"] == "fallback" and "digest" in row["reason"]


def test_signed_but_wrong_raw_binding_aborts_partial_delivery(tmp_path, binary):
    scan, entry, container, mapping = setup_recording(tmp_path, binary, chunk_windows=2)
    table = container / "seek.json"
    doc = json.loads(table.read_bytes())
    doc["records"][1]["parts"][1][3] = "sha256:" + "0"*64
    content = json.dumps(doc).encode()
    table.chmod(0o600)
    table.write_bytes(content)
    mapping["members"][0]["seek_sha256"] = seek.digest(content)
    request, temp = config(tmp_path, binary, mapping)
    audit = {}
    with packed.packed_source(scan, request, temp, audit):
        windows = scan.FastSegmentSource(entry).windows()
        assert next(windows).sequence == 0
        with pytest.raises(ValueError, match="digest"):
            next(windows)
    assert audit["original_windows"] == 0


def test_invalid_map_pin_leaves_stock_source_installed(tmp_path, binary):
    scan, entry, _, mapping = setup_recording(tmp_path, binary)
    original = scan.FastSegmentSource
    (path, _, binary), temp = config(tmp_path, binary, mapping)
    audit = {}
    with packed.packed_source(scan, (path, "sha256:"+"0"*64, binary), temp, audit):
        assert scan.FastSegmentSource is original
        assert len(seen(scan, entry)) == 2
    assert "digest" in audit["fallback"]


def test_strict_packed_eight_checks_an_unused_tail_before_delivery(tmp_path, binary):
    scan, entry, container, mapping = setup_recording(tmp_path, binary, chunk_windows=2, strict=True)
    tail = container / "tail.ci16p"
    content = bytearray(tail.read_bytes())
    content[-1] ^= 128
    tail.chmod(0o600)
    tail.write_bytes(content)
    request, temp = config(tmp_path, binary, mapping)
    audit = {}
    with packed.packed_source(scan, request, temp, audit, strict_eight=True):
        with pytest.raises(ValueError, match="digest"):
            next(scan.FastSegmentSource(entry).windows())
    assert audit["original_windows"] == 0


def test_strict_packed_eight_refuses_a_gap_in_the_map(tmp_path, binary):
    scan, entry, _, mapping = setup_recording(tmp_path, binary, mapped_chunk=1, strict=True)
    request, temp = config(tmp_path, binary, mapping)
    audit = {}
    with packed.packed_source(scan, request, temp, audit, strict_eight=True):
        with pytest.raises(ValueError, match="every acquired member"):
            next(scan.FastSegmentSource(entry).windows())
    assert audit["original_windows"] == 0
