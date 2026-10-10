import pytest

from leo.storage.continuous_window import (
    ContinuousWindowWriter,
    list_checkpoints,
    read_checkpoint,
    run_path,
    write_checkpoint,
    write_publication_failure,
)
from tests.contracts.test_continuous_window_contracts import checkpoint
from tests.scanner.test_continuous_recording import configuration


def test_direct_rotation_keeps_all_quiet_iq_and_global_counter_generation(tmp_path):
    import numpy as np

    from leo.storage.short_window import ShortWindowReader

    config = configuration()
    writer = ContinuousWindowWriter(tmp_path, "ordered", config, radio={})
    for sequence in range(17):
        writer.append(
            sequence=sequence,
            target_id=f"target-{sequence % 8}",
            samples=np.zeros((50000, 2, 2), dtype="<i2"),
            acquisition={
                "generation": 7,
                "sample_start": (1 << 32) + sequence * 100000,
                "global_visit": sequence,
                "target_index": sequence % 8,
            },
            powers=(
                {"receiver_id": 0, "decision": "quiet"},
                {"receiver_id": 1, "decision": "quiet"},
            ),
        )
    assert writer.durable_windows == 16 and writer.segment_index == 2
    final = writer.finish(stop_reason="explicit_stop")
    assert final["durable_windows"] == 17 and final["sealed_segments"] == 3
    records = []
    for index in range(3):
        reader = ShortWindowReader(tmp_path / f"ordered-segment-{index:08d}")
        assert reader.manifest.status == "complete"
        records.extend(reader.windows())
    assert [item.index.acquisition["global_visit"] for item in records] == list(range(17))
    assert all(item.index.acquisition["generation"] == 7 for item in records)
    assert all(item.index.acquisition["sample_start"] >= 1 << 32 for item in records)
    assert all(not item.samples.any() for item in records)


def test_atomic_checkpoint_and_late_publisher_never_overwrite_failure_receipt(tmp_path):
    path = run_path(tmp_path, "run")
    path.mkdir()
    starting = checkpoint()
    write_checkpoint(path, starting)
    assert list_checkpoints(tmp_path) == (starting,)
    failed = starting.model_copy(
        update={"state": "failed", "fault": "publication remained unattested"}
    )
    write_publication_failure(path, failed)
    write_checkpoint(path, starting.model_copy(update={"state": "running"}))
    assert read_checkpoint(tmp_path, "run") == failed
    assert not list(path.glob("*.partial"))
    (path / "publication-failure.json").unlink()
    (path / "run.json").write_text('{"configuration":{}}')
    with pytest.raises(ValueError):
        read_checkpoint(tmp_path, "run")


def test_derived_segment_identity_preflight_and_symlink_checkpoint_rejected(tmp_path):
    with pytest.raises(ValueError):
        ContinuousWindowWriter(tmp_path, "a" * 128, configuration(), radio={})
    path = run_path(tmp_path, "run")
    path.mkdir()
    foreign = tmp_path / "foreign"
    foreign.write_text("unchanged")
    (path / "run.json.partial").symlink_to(foreign)
    with pytest.raises(ValueError, match="symlink"):
        write_checkpoint(path, checkpoint())
    assert foreign.read_text() == "unchanged"


def test_malformed_checkpoint_is_reported_without_hiding_valid_runs(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "run.json").write_text("{}")
    good = tmp_path / "run"
    good.mkdir()
    write_checkpoint(good, checkpoint())
    errors = []
    assert list_checkpoints(tmp_path, on_error=lambda name, error: errors.append(name)) == (
        checkpoint(),)
    assert errors == ["bad"]
