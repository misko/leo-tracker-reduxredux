from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("joint_held_north_raw")


def test_comparison_requires_the_same_assignment_and_worker(trial):
    common = dict(recording="recording", inventory="signed", session="session",
                  compressed_bytes=31, archive={"root": "archive"})
    assignment = common | dict(windows=5, region_file="offer", region_sha256="digest",
                                stock={"raw_authority": "authority"})
    request = common | dict(issued=5, inside_offer="offer", inside_offer_sha256="digest", authority="authority")
    machine = dict(cpu=[2], nice=15)
    trial.validate_workload(request, assignment, machine, machine)
    for wrong in (dict(request, issued=4), dict(request, authority="other"), dict(request, inside_offer_sha256="other")):
        with pytest.raises(ValueError, match="same raw assignment"):
            trial.validate_workload(wrong, assignment, machine, machine)
    with pytest.raises(ValueError, match="same raw assignment"):
        trial.validate_workload(request, assignment, machine, dict(machine, cpu=[3]))


def test_both_calibration_arms_must_be_finite(trial):
    point = dict(latlon=[0.0, 1.0], rf_rms_hz=5.0)
    trial.check_arms({"c0": point, "fitted_c": point})
    for arms in ({"c0": point}, {"c0": point, "fitted_c": dict(point, latlon=None)},
                 {"c0": point, "fitted_c": dict(point, rf_rms_hz=float("nan"))}):
        with pytest.raises(ValueError, match="both calibration arms"):
            trial.check_arms(arms)


def test_factor_audit_counts_edits_and_distinguishes_roundoff_from_changed_epoch(trial, monkeypatch):
    exposure = import_module("anchor_exposure")
    monkeypatch.setattr(exposure, "enroll", lambda _: [(0, 0, 0, "stream", "short", ())])
    original = dict.fromkeys(trial.ROUNDOFF, 0.0) | dict(integer_epoch_sample=40)
    refined = original | {trial.CFO: -0.25}

    def packet(factor):
        return dict(source={"probes": [dict(visit_index=0, receiver_id=0, candidates=[factor])]})

    route = dict(choice={"route": "unfiltered"}, pre_refinement_probes_sha256="pre")
    guarded = refined | {trial.CFO: -0.25 + 1e-9, "fractional_exact_score": 1e-14}
    evidence = trial.compare_factors(packet(original), packet(refined), packet(guarded), route)
    assert evidence["retained_signed_edits_vs_exact_unamended"] == {"short": 1}
    assert evidence["paid_exact_archived_cfo_edits"] == {"short": 1}
    assert not evidence["mismatches"]
    evidence = trial.compare_factors(packet(original), packet(refined), packet(dict(guarded, integer_epoch_sample=41)), route)
    assert evidence["mismatches"] == {"position_rank_gate": 1}


def test_figure_size_matches_old_json_even_when_file_and_pixels_change(trial):
    decoded = dict(size=(100, 50), sha256="file-a", rgba_sha256="pixels-a")
    archived = dict(size=[100, 50], sha256="file-b", rgba_sha256="pixels-b")
    assert trial.compare_figure(decoded, archived) == dict(file_equal=False, pixels_equal=False, dimensions_equal=True)
    assert trial.compare_figure(dict(decoded, size=(90, 50)), archived)["dimensions_equal"] is False
