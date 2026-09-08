import json
import struct
import subprocess

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.evaluate_presence_window_rank import load_dwells, summarize
from tools.native_presence import build_window_ranker, write_probe
from tools.presence_window_rank import write_rank_probe
from tools.qualify_native_presence import digest


def source(directory, rate=2500000):
    directory.mkdir()
    rows, results = [], []
    for index in range(6):
        counter = 10**16 + 37 + index * rate // 50
        path = directory / f"{index}.probe"
        write_probe(path, np.full(rate // 50, index), rate, "lower", counter, ci16=True)
        provenance = {
            "session_id": "test",
            "visit": 13,
            "rx": 1,
            "channel": 2,
            "probe_offset_ms": 20 * index,
            "manifest_sha256": "a" * 64,
        }
        rows.append(
            {
                "file": path.name,
                "sha256": digest(path),
                "rate_hz": rate,
                "edge": "lower",
                "device_counter": str(counter),
                "provenance": provenance,
                "oracle_candidates": [],
            }
        )
        results.append(
            {
                "probe": path.name,
                "provenance": provenance,
                "reference_positive": False,
                "detected": False,
                "matched_reference": False,
                "result": {
                    "rate_hz": rate,
                    "edge": 0,
                    "format": 2,
                    "device_counter": str(counter),
                    "candidates": [],
                },
            }
        )
    (directory / "inputs.json").write_text(json.dumps(rows))
    (directory / "results.json").write_text(json.dumps(results))
    return directory


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_complete_reassembly_keeps_large_counter_and_every_slice(tmp_path, rate):
    rows = list(load_dwells(source(tmp_path / "source", rate)))
    assert len(rows) == 1
    metadata, iq = rows[0]
    assert metadata["counter"] == str(10**16 + 37)
    np.testing.assert_array_equal(iq[:, 0], np.repeat(np.arange(6), rate // 50))
    assert not np.any(iq[:, 1])


@pytest.mark.parametrize(
    "damage",
    ["missing", "offset", "counter", "rx", "hash", "template", "outcome", "outcome_identity"],
)
def test_corrupt_or_incomplete_inventory_is_rejected(tmp_path, damage):
    directory = source(tmp_path / "source")
    inputs_path, result_path = directory / "inputs.json", directory / "results.json"
    rows = json.loads(inputs_path.read_text())
    results = json.loads(result_path.read_text())
    if damage == "missing":
        rows.pop()
    elif damage == "offset":
        rows[0]["provenance"]["probe_offset_ms"] = 20
    elif damage == "counter":
        rows[0]["device_counter"] = "123"
    elif damage == "rx":
        rows[0]["provenance"]["rx"] = 0
    elif damage == "hash":
        rows[0]["sha256"] = "0" * 64
    elif damage == "template":
        path = directory / rows[0]["file"]
        payload = bytearray(path.read_bytes())
        payload[30] ^= 1
        path.write_bytes(payload)
        rows[0]["sha256"] = digest(path)
    elif damage == "outcome":
        results[0]["detected"] = True
    else:
        results[0]["result"]["device_counter"] = "123"
    inputs_path.write_text(json.dumps(rows))
    result_path.write_text(json.dumps(results))
    with pytest.raises(ValueError):
        list(load_dwells(directory))


def test_summary_separates_search_coverage_association_and_unresolved_flags():
    base = {
        "bins": 512,
        "rate_hz": 5000000,
        "reference_positive": [False, True, False, False, False, False],
        "associated": [False, True, False, False, False, False],
        "native_flagged": [False, True, True, False, False, False],
        "order": [2, 1, 0, 3, 4, 5],
        "total_cpu_ms": 1,
    }
    summary = summarize([base])["512"]["5000000"]
    assert summary["first_window_associated_visits"] == 0
    assert summary["reference_positive_visits"] == 1
    assert summary["top_k"]["1"] == {
        "reference_covered": 0,
        "associated": 0,
        "flagged_without_association": 1,
    }
    assert summary["top_k"]["2"] == {
        "reference_covered": 1,
        "associated": 1,
        "flagged_without_association": 0,
    }


def test_standalone_replay_accepts_full_dwell_and_rejects_bad_packet(tmp_path):
    binary = build_window_ranker(tmp_path / "replay", executable=True)
    path = tmp_path / "full.rank"
    rate, counter = 2500000, 10**16 + 37
    payload = struct.pack("<4sIIIIQ", b"LRK1", rate, 0, 300000, 2, counter)
    payload += np.asarray(qin_edge_pilot_frame(rate, "lower"), dtype="<c16").tobytes()
    payload += bytes(300000 * 4)
    write_rank_probe(path, np.zeros((300000, 2), dtype=np.int16), rate, "lower", counter)
    assert path.read_bytes() == payload
    output = subprocess.run(
        [str(binary), str(path), "512", "2"], check=True, capture_output=True, text=True, timeout=10
    )
    rows = [json.loads(line) for line in output.stdout.splitlines()]
    assert len(rows) == 2 and rows[1]["iteration"] == 1
    assert rows[0]["counter"] == str(counter)
    assert rows[0]["scores"] == [0] * 6 and rows[0]["order"] == list(range(6))
    for invalid in (
        payload[:-1],
        payload + b"x",
        payload[:12] + struct.pack("<I", 50000) + payload[16:],
    ):
        path.write_bytes(invalid)
        result = subprocess.run(
            [str(binary), str(path), "512", "2"], capture_output=True, timeout=10
        )
        assert result.returncode == 2 and not result.stdout


@pytest.mark.parametrize("counter", [-1, 2**64 - 1, 1.5, True])
def test_rank_packet_rejects_invalid_intervals_before_creating_output(tmp_path, counter):
    path = tmp_path / "invalid.rank"
    with pytest.raises(ValueError):
        write_rank_probe(path, np.zeros((300000, 2), dtype=np.int16), 2500000, "lower", counter)
    assert not path.exists()
