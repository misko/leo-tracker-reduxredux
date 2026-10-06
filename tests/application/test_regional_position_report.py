from leo.application.regional_position_report import regional_position_document
from leo.application.regional_position_runner import RegionalRunConfiguration, run_regional_position
from tests.application.test_regional_position_runner import Checkpoints, fixture

DIGEST = "sha256:" + "1" * 64


def test_reference_never_selects_result_and_calibration_penalty_changes_ranking(monkeypatch):
    obs, bank, prior, _ = fixture(monkeypatch)
    result = run_regional_position(
        obs,
        bank,
        prior,
        (),
        Checkpoints(),
        configuration=RegionalRunConfiguration(point_budget=16, basins_per_method=1),
    )
    for row in result["finals"]:
        if row["start"] == "associated":
            row["fit"]["objective"] = 100
            row["calibration_penalty"] = 1000
        else:
            row["fit"]["objective"] = 200
            row["calibration_penalty"] = 0
            row["fit"]["vector"][:2] = [20, -30]

    def report(reference):
        return regional_position_document(
            result,
            session_id="scan-1",
            input_digest=DIGEST,
            analysis_digest=DIGEST,
            evidence_digest=DIGEST,
            configuration={},
            windows=len(obs.window_ids),
            reference=reference,
            reference_evidence="evaluation fixture",
        )

    first, second = report((38, -122)), report((39, -121))
    for method, other in zip(first.methods, second.methods, strict=True):
        for arm, other_arm in zip(method.arms, other.arms, strict=True):
            assert arm.completed_starts == 2
            assert arm.selected.selection_score == 200
            assert (arm.selected.east_km, arm.selected.north_km) == (20, -30)
            assert arm.selected.latitude_deg == other_arm.selected.latitude_deg
            assert arm.selected.horizontal_error_m != other_arm.selected.horizontal_error_m


def test_unscored_search_is_explicit_and_does_not_publish_internal_sentinel(monkeypatch):
    obs, bank, prior, _ = fixture(monkeypatch)

    def unavailable(*args, **kwargs):
        raise ValueError("insufficient bootstrap support")

    monkeypatch.setattr("leo.application.regional_position_runner.bootstrap_position", unavailable)
    result = run_regional_position(
        obs, bank, prior, (), Checkpoints(), configuration=RegionalRunConfiguration(point_budget=16)
    )
    doc = regional_position_document(
        result,
        session_id="scan-1",
        input_digest=DIGEST,
        analysis_digest=DIGEST,
        evidence_digest=DIGEST,
        configuration={},
        windows=len(obs.window_ids),
        reference=(38, -122),
        reference_evidence="evaluation fixture",
    )
    assert all(method.state == "insufficient" for method in doc.methods)
    assert all(
        point.objective is None and point.reason
        for method in doc.methods
        for point in method.points
    )
    assert "1e+100" not in doc.model_dump_json()
