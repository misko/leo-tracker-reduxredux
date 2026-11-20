from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import paced_controlled as trial
from tools.pipeline_eval.qualification import paced_controlled_arrival_audit as delays
from tools.pipeline_eval.qualification import paced_controlled_source as stage


def member(seq, samples):
    return dict(
        segment=0,
        sequence=seq,
        iq_sha256="sha256:" + sha256(samples).hexdigest(),
        acquisition=dict(global_visit=seq, sample_start=seq * 2, sample_end=seq * 2 + 2),
        target=dict(rf_center_hz=1000),
        bracket=None,
        clock=dict(monotonic_ns=100 + seq),
        sample_rate_hz=10_000_000,
    )


def test_reader_retains_all_original_bytes_and_validity_metadata(tmp_path, monkeypatch):
    shape = (2, 2, 2)
    first = np.arange(8, dtype="<i2").reshape(shape)
    second = -first
    second = second.astype("<i2", copy=False)
    members = [member(0, first), member(1, second)]
    members[1]["acquisition"]["quality_flags"] = ["invalid"]
    monkeypatch.setattr(stage, "SHAPE", shape)
    monkeypatch.setattr(stage, "WINDOW_BYTES", first.nbytes)
    monkeypatch.setattr(stage, "COUNT", 2)
    data = tmp_path / "samples.ci16"
    data.write_bytes(first.tobytes() + second.tobytes())
    inventory = tmp_path / "members.json.gz"
    stage.pace.writegz(inventory, members)
    stat = data.stat()
    save_json(
        tmp_path / "ready.json",
        dict(
            windows=2,
            bytes=stat.st_size,
            inode=stat.st_ino,
            dev=stat.st_dev,
            mtime_ns=stat.st_mtime_ns,
            window_ledger_sha256=stage._sha(inventory),
        ),
    )
    collected = list(stage.packets(tmp_path))
    assert all(not r[1].samples.flags.writeable for r in collected)
    assert np.array_equal(collected[0][1].samples, first)
    assert np.array_equal(collected[1][1].samples, second)
    assert collected[1][1].acquisition["quality_flags"] == ["invalid"]
    assert collected[1][3] == members[1]["clock"]
    with data.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="inode, size, timestamp"):
        list(stage.packets(tmp_path))


def test_stage_binds_physical_counters_and_exact_sample_digest(monkeypatch):
    samples = np.arange(8, dtype="<i2").reshape(2, 2, 2)
    monkeypatch.setattr(stage, "SHAPE", samples.shape)
    monkeypatch.setattr(stage, "WINDOW_BYTES", samples.nbytes)
    orig = member(0, samples)
    w = SimpleNamespace(
        samples=samples,
        **{
            k: orig[k] for k in ("iq_sha256", "target", "acquisition", "sequence", "sample_rate_hz")
        },
    )
    frame = (0, w, None, orig["clock"])
    event = dict(
        visit=0, sample_start=0, sample_end=2, delivery_clock=orig["clock"], center_hz=1000
    )
    buf, row = stage.window_record(frame, event)
    assert buf.tobytes() == samples.tobytes()
    assert row == orig
    event["sample_end"] = 1
    with pytest.raises(ValueError, match="sample interval"):
        stage.window_record(frame, event)
    event["sample_end"] = 2
    w.samples[1, 1, 1] += 1
    with pytest.raises(ValueError, match="digest"):
        stage.window_record(frame, event)


def test_nominal_counterbalance_includes_both_matched_orders():
    assert trial.ORDER == (
        ("BA", trial.detector.MIXED),
        ("BA", trial.detector.FOUR),
        ("AB", trial.detector.FOUR),
        ("AB", trial.detector.MIXED),
    )


def test_arrival_delay_decomposition_preserves_release_cause_boundaries():
    early = dict(available_ns=0, arrival_ns=1, released_ns=30_000_002)
    late = dict(available_ns=40_000_001, arrival_ns=1, released_ns=50_000_001)
    assert delays.components(early) == (0, 30_000_001)
    assert delays.components(late) == (40_000_000, 10_000_000)
    stat = delays.summarize((early, late))
    assert stat["ready_late_20ms"] == 1
    assert stat["release_late_20ms"] == 2
    assert stat["release_late_20ms_on_time_buffers"] == 1
    with pytest.raises(ValueError, match="released before"):
        delays.components(dict(late, released_ns=2))


def test_cost_contrast_uses_only_same_emitted_physical_visit():
    fast = dict(visit=0, outcome="emitted", native_cpu_ns=3_000_000, native_wall_ns=2_000_000)
    slow = dict(fast, native_cpu_ns=5_000_000)
    result = delays.paired_cost(
        [fast, dict(fast, visit=1)], [slow, dict(slow, visit=1, outcome="queue_drop")]
    )
    assert result["both_emitted"] == 1
    assert result["fused_only"] == 1
    assert result["common_staggered_minus_fused_cpu_p50_ms"] == 2
