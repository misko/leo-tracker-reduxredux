from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import whole_fftw_raw, whole_fftw_results
from tools.pipeline_eval.qualification import whole_fftw_runtime as adapter


def test_runtime_patch_preserves_existing_numpy_dispatch_after_exit():
    original = (
        adapter.parent.MODULE,
        adapter.parent.source_identity,
        adapter.parent.differential_runtime_raw,
    )
    with adapter.activate():
        assert adapter.parent.MODULE == adapter.MODULE
        assert adapter.parent.source_identity is adapter.source_identity
        assert adapter.parent.differential_runtime_raw is whole_fftw_raw
    assert (
        adapter.parent.MODULE,
        adapter.parent.source_identity,
        adapter.parent.differential_runtime_raw,
    ) == original


def test_scout_sidecar_requires_the_qualified_digest(tmp_path):
    path = tmp_path / whole_fftw_raw.SCOUT_NAME
    path.write_bytes(b"unknown detector")
    with pytest.raises(ValueError, match="SHA-256"):
        whole_fftw_raw.library(tmp_path / "hinted.so")


def test_hint_comparison_keeps_invalid_and_changed_receiver_rows_separate():
    def processed(visit, hints, changed):
        return dict(
            visit=visit, status="processed", differential=dict(hints=hints, changed=changed)
        )

    invalid = dict(visit=0, status="invalid_capture")
    python = [invalid, processed(1, (4, 7), (False, True))]
    fftw = [invalid, processed(1, (4, 8), (True, True))]
    assert whole_fftw_results.compare_hints(python, fftw) == dict(
        compared_receiver_visits=2,
        different_rank_one_hints=1,
        different_hint_insertions=1,
    )
    with pytest.raises(ValueError, match="visit boundaries"):
        whole_fftw_results.compare_hints(python, [invalid, processed(2, (4, 7), (False, True))])


def test_pending_preserves_failed_service_without_reusing_an_unsettled_run(tmp_path, monkeypatch):
    monkeypatch.setattr(whole_fftw_results, "trial", SimpleNamespace(CASES=("holdout",)))
    case = tmp_path / "holdout"
    candidate = case / "candidate"
    candidate.mkdir(parents=True)
    (candidate / "service-launch.json").touch()
    (case / "candidate-failure.json").touch()
    assert whole_fftw_results.pending(tmp_path) == ["holdout"]
    (candidate / "service.json").write_text('{"exit_code": 124}')
    assert whole_fftw_results.pending(tmp_path) == []
