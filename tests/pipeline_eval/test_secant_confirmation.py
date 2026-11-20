import pytest

from tools.pipeline_eval.qualification import phase_confirmation as phase
from tools.pipeline_eval.qualification import secant_confirmation as secant


def test_secant_roster_is_the_first_four_of_each_frozen_confirmation_group():
    public = phase.frozen_inputs()
    ds26, ds29 = phase.confirmation_ids(public)
    roster = secant.roster(public)
    assert roster["cases"] == ds26[:4] + ds29[:4]
    assert roster["ds26_in_hash_order"] == ds26[:4]
    assert roster["ds29"] == ds29[:4]
    assert set(roster["case_bindings"]) == set(roster["cases"])
    assert not set(roster["cases"]) & set(phase.TIMING_IDS)


def test_secant_requires_the_cli_identity_and_original_refresh_history(monkeypatch):
    monkeypatch.setattr(secant, "_cli_digest", lambda: "combined CLI identity")
    ident = "DS26-0142"
    case = {"id": ident}
    sources = {"v5_secant_fit.py": "solver source", "orbit_projector.c": "kernel"}
    row = dict(
        id=ident,
        method=secant.METHOD,
        source_sha256=sources,
        implementation_sha256="combined CLI identity",
        deadline_s=phase.CAP_S,
        cpu=16,
        worker_wall_s=30,
        input_sha256=phase.projector_roof.input_hash(case),
        result=dict(
            status="ok",
            boundary="full compact cavity",
            arms={arm: {"latlon": [10.0, -20.0]} for arm in phase.ARMS},
            metrics=dict(
                kernel_sha256="kernel",
                initial_phase_refresh_counts=[5, 5, 5],
                position_optimizer={"calls": 15},
            ),
        ),
    )
    assert secant._validate(row, ident, case, {}, sources) is row
    row["result"]["metrics"]["initial_phase_refresh_counts"][0] = 6
    with pytest.raises(ValueError, match="original refresh history"):
        secant._validate(row, ident, case, {}, sources)
    row["result"]["metrics"]["initial_phase_refresh_counts"][0] = 5
    row["implementation_sha256"] = "solver source"
    with pytest.raises(ValueError, match="paired compact cavity worker"):
        secant._validate(row, ident, case, {}, sources)


def test_six_case_source_lock_matches_all_five_live_modules():
    assert secant.frozen_sources() == phase.pinned_sources(secant.METHOD)
