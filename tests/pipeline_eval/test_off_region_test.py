import pytest

from tools.pipeline_eval.qualification import off_region_eval as evaluation
from tools.pipeline_eval.variants import off_region_test as variant


def test_group_rotation_preserves_offer_spacing_at_the_longitude_seam():
    offers = [("one", (14.5, 171.0)), ("two", (21.0, 175.0))]
    assert variant._rotated_offers(offers, 1) == [(14.5, -171.0), (21.0, -167.0)]
    assert variant._rotated_offers(offers, variant.ROTATION_COUNT) == [p for _, p in offers]


@pytest.mark.parametrize("support, expected_veto, expected_tiles", [(3, True, 1), (2, False, 76)])
def test_rotation_matches_use_same_track_and_support_budget(
    monkeypatch, support, expected_veto, expected_tiles
):
    obs = dict(
        duration_s=20,
        tracks=[
            dict(
                times=list(range(12)),
                values=list(range(12)),
                rf_hz=11.325e9,
                receiver=1,
                channel=3,
            )
        ],
    )
    offers = [dict(id=str(i), center=[20 + i, 50 + i]) for i in range(4)]
    monkeypatch.setattr(variant.grid, "prepare_sky", lambda observation, catalog: catalog)
    monkeypatch.setattr(variant.grid, "make_tile", lambda sky, center: (sky, center))

    def nominate(tile, usable):
        assert tile[0] == b"catalogue"
        assert usable[0]["values"] == tuple(range(12))
        return dict(training_score=0.85, held_score=0.75, held_orbits=support)

    monkeypatch.setattr(variant.arc_validation, "_nomination", nominate)
    control = variant._longitude_control(obs, offers, b"catalogue", 0.75)
    assert control["veto"] is expected_veto
    assert control["null_tiles_tested"] == expected_tiles


def test_veto_changes_acceptance_and_preserves_the_forced_diagnostic(monkeypatch):
    winner = dict(latlon=[25.5, 28.0], held_rms_hz=196, held_score=0.28)
    evidence = dict(region_accepted=True, selected_region_id="kept")
    monkeypatch.setattr(
        variant.arc_validation, "solve", lambda *args: (winner, "accepted", evidence)
    )
    monkeypatch.setattr(variant, "_longitude_control", lambda *args: dict(veto=True))
    baseline, candidate = variant.compare({}, [], b"")
    assert baseline["metrics"]["region_accepted"]
    assert candidate["reason"] == variant.NULL_REJECTION
    assert candidate["metrics"]["selected_region_id"] == "kept"
    assert not candidate["metrics"]["region_accepted"]
    assert candidate["arms"]["c0"] == candidate["arms"]["fitted_c"]
    assert candidate["arms"]["c0"]["latlon"] is None
    assert candidate["arms"]["c0"]["forced_latlon"] == winner["latlon"]


def test_score_does_not_open_labels_without_prediction_seal(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "_verify_sources", lambda _: None)

    def unexpected_answers(_):
        pytest.fail("labels were opened without a prediction seal")

    monkeypatch.setattr(evaluation, "_answers", unexpected_answers)
    with pytest.raises(FileNotFoundError, match="prediction-lock.json"):
        evaluation.score(tmp_path, tmp_path)

    (tmp_path / "prediction-lock.json").write_text('{"files": {}}')
    monkeypatch.setattr(evaluation, "_lock", lambda _: {"predictions.jsonl.gz": "mismatch"})
    with pytest.raises(ValueError, match="prediction seal"):
        evaluation.score(tmp_path, tmp_path)
