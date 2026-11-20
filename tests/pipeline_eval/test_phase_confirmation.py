import pytest

from tools.pipeline_eval.qualification import phase_confirmation as phase


def test_frozen_hash_roster_is_independent_of_records_and_timing():
    public = phase.frozen_inputs()
    ds26, ds29 = phase.confirmation_ids(public)
    assert len(ds26) == 16
    assert ds26[:3] == ["DS26-0142", "DS26-0223", "DS26-0301"]
    assert ds26[-1] == "DS26-0261"
    assert ds29 == ["DS29-0127", "DS29-0316", "DS29-0357", "DS29-0519", "DS29-0604"]
    assert not set(phase.TIMING_IDS) & set(ds26 + ds29)
    assert phase.confirmation_ids(dict.fromkeys(reversed(public))) == (ds26, ds29)


def test_candidate_budget_and_kernel_stay_bound(monkeypatch):
    monkeypatch.setattr(
        phase, "module_name", lambda _: "tools.pipeline_eval.variants.v5_two_refresh"
    )
    case = {"id": "DS26-0142"}
    binding = dict(native_sha256="native", catalog_sha256="catalogue")
    sources = {"v5_two_refresh.py": "candidate", "orbit_projector.c": "kernel"}
    result = dict(
        status="ok",
        boundary="full native through cavity",
        metrics=dict(kernel_sha256="kernel", outer_phase_limit=2),
        arms={arm: {"latlon": [22.0, -70.0]} for arm in phase.ARMS},
    )
    row = dict(
        id=case["id"],
        method=phase.METHOD,
        deadline_s=480,
        source_sha256=sources,
        cpu=16,
        worker_wall_s=10.0,
        implementation_sha256="candidate",
        input_sha256=phase.projector_roof.input_hash(case),
        result=result,
        **binding,
    )
    assert phase._validate_candidate(row, case["id"], case, binding, sources) is row
    result["metrics"]["outer_phase_limit"] = 3
    with pytest.raises(ValueError, match="paired compact cavity worker"):
        phase._validate_candidate(row, case["id"], case, binding, sources)


def test_timeout_retains_actual_elapsed_and_no_coordinate(monkeypatch):
    monkeypatch.setattr(
        phase, "module_name", lambda _: "tools.pipeline_eval.variants.v5_two_refresh"
    )
    case = {"id": "DS29-0357"}
    result = dict(
        status="timed_out", reason="worker exceeded 480 seconds", metrics={}, boundary="worker"
    )
    row = dict(
        id=case["id"],
        method=phase.METHOD,
        deadline_s=480,
        source_sha256={},
        cpu=19,
        worker_wall_s=480.1,
        input_sha256=phase.projector_roof.input_hash(case),
        result=result,
    )
    assert phase._validate_candidate(row, case["id"], case, {}, {}) == row


def test_requires_prediction_lock_before_reading_geography(tmp_path, monkeypatch):
    def forbidden():
        pytest.fail("opened position references before seal verification")

    monkeypatch.setattr(phase.projector_roof, "roster", forbidden)
    with pytest.raises(FileNotFoundError, match="receipt.json"):
        phase.score(tmp_path)
    (tmp_path / "receipt.json").write_text('{"files": {"plan.json": "untrusted"}}')
    with pytest.raises(ValueError, match="no intact confirmation prediction seal"):
        phase.score(tmp_path)
