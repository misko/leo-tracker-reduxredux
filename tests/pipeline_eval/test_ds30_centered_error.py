import json
from math import hypot

import pytest

from reports.ALGO08.v3 import ds30_centered_error as trial
from reports.ALGO08.v3.ds30_centered_error import analyze, pending_pairs
from reports.ALGO08.v3.ds30_position_moments import decompose, east_north_km
from tools.pipeline_eval.scoring import distance_km


@pytest.mark.parametrize(("reference", "endpoint", "direction"), (
    ((0, 0), (0, 10), (1, 0)),
    ((0, 0), (0, -10), (-1, 0)),
    ((40, 30), (45, 30), (0, 1)),
    ((40, 30), (35, 30), (0, -1)),
    ((0, 179.5), (0, -179.5), (1, 0)),
))
def test_chart_has_the_scoring_radius_and_local_direction(reference, endpoint, direction):
    result = east_north_km(reference, endpoint)
    distance = distance_km(reference, endpoint)
    assert hypot(*result) == pytest.approx(distance, rel=5e-12)
    assert result == pytest.approx(tuple(distance*axis for axis in direction), abs=5e-12)


def test_zero_and_antipodal_endpoints_have_explicit_semantics():
    assert east_north_km((53, 42), (53, 42)) == (0., 0.)
    with pytest.raises(ValueError, match="antipode"):
        east_north_km((0, 0), (0, 180))


def test_mean_displacement_does_not_change_centered_spread():
    values = [(1., 0.), (-1., 0.), (0., 1.), (0., -1.)]
    translated = [(e+3., n-4.) for e, n in values]
    original, shifted = decompose(values), decompose(translated)
    assert original["radial_mse_km2"] == original["centered_mse_km2"] == 1.
    assert shifted["radial_mse_km2"] == 26.
    assert shifted["squared_mean_offset_km2"] == 25.
    assert shifted["centered_mse_km2"] == 1.
    assert shifted["max_identity_residual_km2"] == 0.


def test_shared_scored_support_excludes_failed_and_unscored_fixes_only_from_scatter():
    def receipt(fix, *, outcome=None):
        return dict(outcome=outcome or ("complete" if fix else "withheld"),
                    arms={arm: dict(latlon=fix) for arm in ("c0", "fitted_c")})

    one = dict(installed=receipt((0., .1)), successor=receipt((0., .2)))
    candidate_only = dict(installed=receipt(None, outcome="solver_failed"), successor=receipt((0., .5)))
    captures = [("one", (0., 0.), one), ("unscored", None, one), ("candidate_only", (0., 0.), candidate_only)]
    result = analyze(captures)
    assert result["assigned"] == 3
    assert result["outcomes"]["installed"]["solver_failed"] == 1
    for arm in result["arms"].values():
        assert arm["shared"] == ["one"]
        assert arm["fixes"] == {"installed": 2, "successor": 3}
        assert arm["scored"] == {"installed": 1, "successor": 2}
        assert all(row["n"] == 1 and row["centered_mse_km2"] == 0 for row in arm["builds"].values())


def test_zero_shared_fixes_retains_total_return_counts_without_scatter_estimates():
    arm = {name: {"latlon": None} for name in trial.ARMS}
    result = analyze([("one", (0., 0.), {role: {"outcome": "withheld", "arms": arm} for role in trial.BUILDS})])
    assert result["assigned"] == 1
    for entry in result["arms"].values():
        assert entry["fixes"] == {"installed": 0, "successor": 0}
        assert entry["builds"] == {"installed": {"n": 0}, "successor": {"n": 0}}
        assert entry["successor_minus_installed"] is None


def test_pending_prospective_respects_all_pair_seals_before_reading_any_export(tmp_path, monkeypatch):
    order = ["installed", "successor"]
    entries = [{"case": case, "order": order} for case in trial.INITIAL+trial.PROSPECTIVE]
    monkeypatch.setattr(trial, "campaign_order", lambda campaign: entries)
    observed = {"state": "observed_pair", "verified_pair": True, "chronological": True, "actual_order": order}
    root = tmp_path/"cases"
    first = root/trial.PROSPECTIVE[0]
    first.mkdir(parents=True)
    path = first/"pair.json"
    path.write_text(json.dumps(observed))
    reserved = entries[len(trial.INITIAL):]
    assert pending_pairs(tmp_path, reserved) == dict.fromkeys(trial.PROSPECTIVE[1:], "no_pair_receipt")
    # No export or scored receipts exist in this fixture. Pending checks need no endpoint.
    assert trial.prospective(tmp_path)["ready"] is False
    path.write_text(json.dumps(observed | {"actual_order": order[::-1]}))
    with pytest.raises(ValueError, match="frozen order"):
        pending_pairs(tmp_path, reserved)


def test_prospective_requires_current_combined_seal_and_identical_worker_rows(tmp_path, monkeypatch):
    entries = [{"case": case} for case in trial.INITIAL+trial.PROSPECTIVE]
    monkeypatch.setattr(trial, "campaign_order", lambda campaign: entries)
    monkeypatch.setattr(trial, "pending_pairs", lambda campaign, entries: {})
    rows = [dict(case=case, algorithm=role, verified_pair=True) for case in trial.PROSPECTIVE for role in trial.BUILDS]
    body = "\n".join(json.dumps(row) for row in rows).encode()
    (tmp_path/"rows.jsonl").write_bytes(body)
    seal_path = tmp_path/"rows-with-relocations-seal.json"
    seal = dict(plan_sha256=trial.PLAN, ledger_snapshot_sha256="previous export", combined_sha256="previous combined")
    seal_path.write_text(json.dumps(seal))
    assert trial.prospective(tmp_path)["pending"] == {"combined_export": "ordinary_snapshot_not_yet_sealed"}

    combined = b"\n".join((body.splitlines())[:-1])
    (tmp_path/"rows-with-relocations.jsonl").write_bytes(combined)
    seal_path.write_text(json.dumps(seal | dict(ledger_snapshot_sha256=trial.digest(body), combined_sha256=trial.digest(combined))))
    with pytest.raises(ValueError, match="cover all six"):
        trial.prospective(tmp_path)
