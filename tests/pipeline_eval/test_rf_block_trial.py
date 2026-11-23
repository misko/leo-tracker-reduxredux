from importlib import import_module
import gzip
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools.pipeline_eval.variants.carrier_continuation import Continuation


def proposals(count):
    for i in range(count):
        for receiver in (0, 1):
            base = 1200 + 200 * i
            yield dict(receiver_id=receiver, valid_start_counter=i * 1_000_000, visit_index=i + 3,
                       channel=i % 3, edge="upper", actual_rf_hz=1234567 + i % 3,
                       candidates=[dict(fractional_tracking_cfo_hz=base + 3000 * rank,
                                        fractional_margin=.8 - .2 * rank, candidate_rank=rank)
                                   for rank in range(2)])


def replay(rows, paid):
    continuation = Continuation()
    result = {}
    for probe in rows:
        candidates = probe["candidates"] if probe["visit_index"] in paid else []
        _, index, _ = continuation.select(dict(probe, candidates=candidates))
        result[(probe["visit_index"], probe["receiver_id"])] = None if index is None else candidates[index]
    return result


def test_rf_block_warmup_reproduces_actual_continuation(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    rows = list(proposals(300))
    keep, paid, slots = import_module("rf_block_trial").schedule(rows)
    assert len(slots) == 3 and 0 < len(keep) < len(paid) < 300
    assert len(paid - keep) == 24
    reference = replay(rows, set(range(3, 303)))
    observed = replay(rows, paid)
    assert all(reference[v, rx] == observed[v, rx] for v in keep for rx in (0, 1))
    assert any(reference[v, 1] is not None for v in keep)
    assert all(v >= 3 for v in keep)


def test_rf_schedule_ignores_outcomes_and_rejects_inconsistent_pairs(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    schedule = import_module("rf_block_trial").schedule
    rows = list(proposals(32))
    assert schedule(rows) == schedule([dict(row, candidates=[]) for row in rows])
    with pytest.raises(ValueError, match="Malformed"):
        schedule([dict(rows[0], actual_rf_hz=22), *rows[1:]])


def test_all_timed_decisions_bind_to_archived_solver_outputs():
    folder = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/measurements"
    summary = json.loads((folder / "rf-block.json").read_bytes())["cases"]
    raw = json.loads(gzip.decompress((folder / "rf-block-solves.json.gz").read_bytes()))
    assert summary.keys() == raw.keys() == {"DS30-0008", "south-containing", "south-far"}
    for case, source in raw.items():
        row = summary[case]
        assert sha256(source.encode()).hexdigest() == row["decision"]["full_solver_receipt_sha256"]
        full = json.loads(source)
        assert full["identity"]["native_sha256"] == row["mask"]["packet_digest"]
        assert full["identity"]["original_native_sha256"] == row["input"]["native_sha256"]
        assert full["result"]["status"] == row["decision"]["status"]
        assert row["quality_screen"] == (case == "south-far")
