import json
from pathlib import Path

import pytest

from archive_ds23_completed_recovery_results import archive_result, digest, terminal_paths


def result(tmp_path, status="complete"):
    path = tmp_path / "run/DS23-0001/result.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(status=status, scientific_values=[1., 2., 3.])))
    return path


def test_exact_bytes_survive_atomic_absolute_symlink_replacement(tmp_path, monkeypatch):
    import archive_ds23_completed_recovery_results as module

    source = result(tmp_path)
    expected, original = digest(source), source.read_bytes()
    replace = module.os.replace
    observed = []
    def check_replace(link, final):
        assert Path(final) == source
        assert source.read_bytes() == original and not source.is_symlink()
        assert Path(link).is_symlink() and Path(link).read_bytes() == original
        observed.append(True)
        replace(link, final)
    monkeypatch.setattr(module.os, "replace", check_replace)
    receipt = archive_result(source, tmp_path / "bulk")
    assert observed == [True]
    assert source.is_symlink() and source.readlink().is_absolute()
    assert source.read_bytes() == original and receipt["sha256"] == expected
    assert archive_result(source, tmp_path / "bulk")["cached"]


def test_conflicting_archive_preserves_the_original_file(tmp_path):
    source = result(tmp_path)
    expected = source.read_bytes()
    destination = tmp_path / "bulk/DS23-0001/result.json"
    destination.parent.mkdir(parents=True)
    destination.write_text("different scientific bytes")
    with pytest.raises(ValueError, match="different scientific bytes"):
        archive_result(source, tmp_path / "bulk")
    assert not source.is_symlink() and source.read_bytes() == expected


def test_active_results_and_checkpoint_names_are_rejected(tmp_path):
    source = result(tmp_path, "running")
    with pytest.raises(ValueError, match="active result"):
        archive_result(source, tmp_path / "bulk")
    checkpoint = source.with_name("checkpoint.json")
    checkpoint.write_text(source.read_text())
    with pytest.raises(ValueError, match="only a DS23 result"):
        archive_result(checkpoint, tmp_path / "bulk")
    assert source.exists() and checkpoint.exists()


def test_protected_destination_symlink_cannot_receive_writes(tmp_path, monkeypatch):
    import archive_ds23_completed_recovery_results as module

    source = result(tmp_path)
    protected = tmp_path / "protected"
    protected.mkdir()
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    (bulk / "DS23-0001").symlink_to(protected)
    monkeypatch.setattr(module, "QNAP", protected)
    with pytest.raises(ValueError, match="QNAP paths are read-only"):
        archive_result(source, bulk)
    assert list(protected.iterdir()) == []
    assert source.exists() and not source.is_symlink()


def test_new_result_without_completion_receipt_is_not_an_archive_candidate(tmp_path):
    source = result(tmp_path)
    run = source.parent.parent
    partial = run / "DS23-0002/result.json"
    partial.parent.mkdir()
    partial.write_text("{still writing")
    (run / "durable_recovery_plan.json").write_text(json.dumps(dict(
        original_terminal_cases=["DS23-0001"], interrupted_cases=[])))
    (run / "progress.json").write_text(json.dumps(dict(receipts=[])))
    assert terminal_paths(run) == [source]
