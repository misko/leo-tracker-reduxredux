from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from alternate_original_raw import omitted_index, plan, scan_report
from alternate_original_raw_score import factor_delta


def test_parity_follows_original_compressed_members_across_segments():
    def segment(entry):
        chunks = [SimpleNamespace(first_sequence=i, window_count=1,
                                  model_dump=lambda *, mode, index=i: {"chunk_index": index})
                  for i in range(entry["windows"])]
        manifest = SimpleNamespace(chunks=chunks, schema_version=2, window_ms=20,
                                   sample_rate_hz=10_000_000, window_count=entry["windows"])
        return SimpleNamespace(receiver_ids=(0, 1), reader=SimpleNamespace(manifest=manifest))

    inventory = dict(window_count=3, segments=[dict(path=f"/segment{j}", scope=str(j),
                                                   manifest_digest=f"manifest{j}", windows=length)
                                              for j, length in enumerate((1, 2))])
    _, members = plan(inventory, segment)
    assert [(m["ordinal"], m["first_visit"], m["stop_visit"], m["retained"]) for m in members] == [
        (0, 0, 1, True), (1, 1, 2, False), (2, 2, 3, True)]


def test_omitted_index_must_be_authenticated_and_consecutive(tmp_path):
    model = SimpleNamespace(model_validate_json=lambda data: SimpleNamespace(**json.loads(data)))
    body = json.dumps(dict(sequence=64, receiver_count=2, payload_offset_bytes=0,
                           payload_bytes=16, sample_count=2)).encode()
    path = tmp_path / "index.jsonl"
    path.write_bytes(body)
    member = dict(first_sequence=64, window_count=1, uncompressed_bytes=16, index_bytes=len(body),
                  index_sha256="sha256:" + sha256(body).hexdigest())
    assert omitted_index(path, member, model)[0].sequence == 64
    with pytest.raises(ValueError, match="geometry"):
        omitted_index(path, dict(member, first_sequence=65), model)
    path.write_bytes(body.replace(b"64", b"65"))
    with pytest.raises(ValueError, match="signed manifest"):
        omitted_index(path, member, model)


def test_skipped_acquisition_does_not_change_invalid_capture():
    def report(*args):
        return {"counts": {"processed": 1, "invalid_capture": 1, "skipped_fast_score": 0}, "window_count": 3}

    native = {"provenance": {"research_sampling": {"skipped_acquisition_windows": [1]}}}
    summary = scan_report(report, "recording", "run", native)
    assert summary["counts"] == {"processed": 1, "invalid_capture": 1, "skipped_fast_score": 0,
                                 "skipped_acquisition": 1}


def test_factor_change_preserves_the_original_slots_and_counts():
    before = [dict(visit_index=i, receiver_id=0, candidates=factors) for i, factors in enumerate(([1], [], [3]))]
    after = [dict(row, candidates=factors) for row, factors in zip(before, ([], [2], [4]), strict=True)]
    result = factor_delta(before, after)
    assert result["factor_counts"] == [2, 2]
    assert result["differences"] == {"lost": [(0, 0)], "added": [(1, 0)], "changed": [(2, 0)]}
    with pytest.raises(ValueError, match="ordered signed receiver slots"):
        factor_delta(before, after[::-1])
