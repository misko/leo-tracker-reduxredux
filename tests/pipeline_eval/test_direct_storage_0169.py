from types import SimpleNamespace
from hashlib import sha256
import json

import pytest

from reports.ALGO08.v3 import direct_storage_0169 as trial
from reports.ALGO08.v3.mixed_aperture_receiver import StereoSchedule


def test_frozen_second_member_cannot_read_neighbor_or_wider_blob():
    fields = dict(chunk_index=1, first_sequence=64, window_count=64, uncompressed_bytes=trial.first.DECODED,
                  payload_relative_path=trial.PAYLOAD, compressed_bytes=trial.COMPRESSED,
                  compressed_sha256=trial.PAYLOAD_PIN, index_relative_path=trial.INDEX,
                  index_bytes=trial.INDEX_BYTES, index_sha256=trial.INDEX_PIN)
    model = SimpleNamespace(receiver_ids=(0, 1), sample_rate_hz=10_000_000)
    for bad in (dict(chunk_index=0), dict(first_sequence=128), dict(compressed_bytes=82_000_001),
                dict(index_relative_path="windows-000002.jsonl"), dict(compressed_sha256="sha256:changed")):
        model.chunks = [object(), SimpleNamespace(**(fields | bad))]
        with pytest.raises(ValueError):
            trial.member_one(model)
    model.chunks = [object(), SimpleNamespace(**fields), object()]
    assert trial.member_one(model) is model.chunks[1]


def test_seed_counts_only_admitted_stereo_pairs_and_carries_next_anchor():
    def probe(visit, receiver):
        return dict(visit_index=visit, receiver_id=receiver, edge="lower", channel=1, actual_rf_hz=1_000.0,
                    valid_start_counter=20 * visit)

    paid = [0, 1, 5, 11, 27, 37, 44, 58]
    prefix = dict(iq=["verified"] * 64, native_schedule=dict(rule=trial.FULL_RULE, installed_sha256=trial.INSTALLED_SHA,
                  short_primary_sha256=trial.SHORT_SHA, streams=[dict(edge="lower", channel=1, rf_hz=1_000.,
                  admitted=8, final_valid_counter=20 * 58)]), packet=dict(clock_anchor={"seen": True},
                  delivery_clocks=[{}] * 64, provenance=dict(window_count=64, processed_windows=8, invalid_capture=56),
                  source=dict(probes=[probe(i, r) for i in paid for r in (0, 1)])))
    scheduler = StereoSchedule(full_coverage=True)
    scheduler.streams.update(trial.seed_streams(prefix))
    target = dict(edge="lower", channel=1, lnb_lo_hz=900)
    capture = dict(actual_if_center_hz=100, sample_start=20 * 64)
    assert scheduler.visit("lower", target, capture) == (8, "full")
    assert scheduler.visit("lower", target, dict(capture, sample_start=20 * 65)) == (9, "short_primary")
    prefix["native_schedule"]["streams"][0]["admitted"] = 16
    with pytest.raises(ValueError, match="scheduling state differs"):
        trial.seed_streams(prefix)


def test_wait_budget_leaves_nested_io_and_hash_out_of_disjoint_total():
    def clock(wall, cpu):
        return dict(wall_ns=wall, cpu_ns=cpu)

    stages = dict(index_member=clock(5, 3), index_sha256=clock(1, 1),
                  compressed_descriptor=clock(500_000_000, 20_000_000),
                  payload_read_syscalls=clock(499_000_000, 19_000_000), compressed_sha256=clock(20, 20),
                  zstd_read=clock(120, 120), decoded_window_sha256=clock(40, 40),
                  decoded_member_sha256_final=clock(10, 10))
    raw = dict(acquire=clock(600_000_000, 120_000_000), stages=stages,
               native_wall_ns={"full": 99_999_000}, native_cpu_ns={"full": 99_999_000})
    result = trial.result_budget(raw)
    assert result["descriptor_off_cpu_ns"] == 480_000_000
    assert result["wall_without_descriptor_off_cpu_ns"] == 120_000_000
    assert result["ideal_member_local_overlap_floor_ns"] == 500_000_000
    assert result["disjoint_remainder"] == {"wall_ns": 805, "cpu_ns": 807}
    assert 0 < result["hide_fraction"] < 1


def test_archived_metadata_uses_the_same_original_prefix_bytes(monkeypatch, tmp_path):
    monkeypatch.setattr(trial, "PREFIX_PACKET", tmp_path / "not-staged.json")
    contents = trial.prefix_bytes()
    assert sha256(contents).hexdigest() == trial.PREFIX_PIN
    assert sum(count for count, _ in trial.seed_streams(json.loads(contents)).values()) == 51
