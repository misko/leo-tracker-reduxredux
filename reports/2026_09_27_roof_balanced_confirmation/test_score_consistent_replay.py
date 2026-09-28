import json

import pytest

import score_consistent_replay as score


def saved_branch():
    rows = [
        {"east_km": 0., "north_km": 0., "latitude_deg": 1., "longitude_deg": 2.,
         "scores": {"D": 1., "D_plus_geometry": 3.}},
        {"east_km": 1., "north_km": 0., "latitude_deg": 1., "longitude_deg": 2.,
         "scores": {"D": 2., "D_plus_geometry": 2.}},
    ]
    return {"grid_count": 2, "point_components": rows,
            "arms": {"D": {"selected": rows[0]},
                     "D_plus_geometry": {"selected": rows[1]}}}


def replay_branch():
    rows = [
        {"east_km": 0., "north_km": 0., "latitude_deg": 1., "longitude_deg": 2.,
         "variant_scores": {"old": {"D": 1., "D_plus_geometry": 3.},
                            "consistent": {"D": 1., "D_plus_geometry": 1.}}},
        {"east_km": 1., "north_km": 0., "latitude_deg": 1., "longitude_deg": 2.,
         "variant_scores": {"old": {"D": 2., "D_plus_geometry": 2.},
                            "consistent": {"D": 2., "D_plus_geometry": 4.}}},
    ]
    branch = {"grid_count": 2, "point_components": rows,
              "selected": {"old": rows[1], "consistent": rows[0]}}
    branch["parity"] = score.replay.parity_report(saved_branch(), rows)
    return branch


def test_branch_gate_accepts_exact_inventory_parity_and_minima():
    result = score.validate_branch(saved_branch(), replay_branch())
    assert result["D"]["east_km"] == 0.
    assert result["oldJoint"]["east_km"] == 1.
    assert result["newJoint"]["east_km"] == 0.


def test_source_selected_may_retain_tracks_but_lightweight_fields_must_match():
    saved = saved_branch()
    saved["arms"]["D"]["selected"] = {
        **saved["arms"]["D"]["selected"], "tracks": [{"track_id": "detail"}]}
    assert score.validate_branch(saved, replay_branch())["D"]["east_km"] == 0.
    saved["arms"]["D"]["selected"]["east_km"] = 9.
    with pytest.raises(ValueError, match="minimum is not reproducible"):
        score.validate_branch(saved, replay_branch())


def test_branch_gate_rejects_missing_or_duplicate_inventory():
    result = replay_branch()
    result["point_components"].pop()
    with pytest.raises(ValueError, match="inventory differs"):
        score.validate_branch(saved_branch(), result)
    result = replay_branch()
    result["point_components"][1]["east_km"] = 0.
    with pytest.raises(ValueError, match="inventory differs"):
        score.validate_branch(saved_branch(), result)


def test_branch_gate_rejects_nonfinite_or_changed_scores():
    result = replay_branch()
    result["point_components"][0]["variant_scores"]["old"]["D"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        score.validate_branch(saved_branch(), result)
    result = replay_branch()
    result["point_components"][0]["variant_scores"]["old"]["D"] += 2e-7
    with pytest.raises(ValueError, match="parity failed"):
        score.validate_branch(saved_branch(), result)


def test_branch_gate_rejects_nonfinite_or_changed_geographic_coordinate():
    result = replay_branch()
    result["point_components"][0]["latitude_deg"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite replay coordinate"):
        score.validate_branch(saved_branch(), result)
    result = replay_branch()
    result["point_components"][0]["longitude_deg"] += .01
    with pytest.raises(ValueError, match="differs from saved grid"):
        score.validate_branch(saved_branch(), result)


def test_branch_gate_rejects_changed_saved_minimum():
    result = replay_branch()
    result["selected"]["consistent"] = result["point_components"][1]
    with pytest.raises(ValueError, match="minimum is not reproducible"):
        score.validate_branch(saved_branch(), result)


def test_summary_reports_each_prior_separately():
    rows = []
    for prior in ("sacramento", "reno"):
        rows.extend([
            {"prior": prior, "D_error_km": 3., "oldJoint_error_km": 2.,
             "newJoint_error_km": 1., "new_minus_old_km": -1., "new_minus_D_km": -2.},
            {"prior": prior, "D_error_km": 1., "oldJoint_error_km": 1.,
             "newJoint_error_km": 2., "new_minus_old_km": 1., "new_minus_D_km": 1.},
        ])
    actual = score.summarize(rows)
    assert set(actual) == {"sacramento", "reno"}
    assert actual["reno"]["old_to_new"] == {"improved": 1, "worsened": 1, "tied": 0}


def test_missing_or_incomplete_cohort_withholds_reference_parse(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(score, "HERE", tmp_path)
    entries = [{"session_id": sid} for sid in ("a", "b", "c", "d")]
    monkeypatch.setattr(score.balanced, "inputs", lambda: (entries, {}))
    (tmp_path / "manifest.json").write_text("must not be parsed")
    (tmp_path / "consistent-replay-a.json").write_text(json.dumps({"finished": False}))
    score.main()
    output = json.loads(capsys.readouterr().out)
    assert output["complete"] is False
    assert set(output["pending_sessions"]) == {"a", "b", "c", "d"}
    assert not (tmp_path / "consistent-replay-distances.json").exists()
