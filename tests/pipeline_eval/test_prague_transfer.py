from zipfile import ZipFile

import numpy as np
import pytest

from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.qualification import prague_transfer_results as results
from tools.pipeline_eval.qualification import prague_transfer_trial as trial
from tools.pipeline_eval.variants import prague_transfer as model


@pytest.fixture
def synthetic_arcs():
    times = np.arange(55, dtype=float)
    receiver = geodetic_to_ecef_km(*model.CITY, 250)
    location = model.geographic([-7.5, 5])
    geometries = (
        ([500, -100, 400], [1, 7, 1]),
        ([400, 0, 500], [-5, 1, 6]),
    )
    arcs = []
    for displacement, speed in geometries:
        velocity = np.broadcast_to(speed, (len(times), 3))
        position = receiver + displacement + (times[:, None] - 20) * velocity
        arc = model.Arc(times, np.zeros_like(times), position, velocity)
        measured = model.carrier_doppler(location, arc)[0] + 997
        arcs.append(model.Arc(times, measured, position, velocity))
    return tuple(arcs)


def test_one_rf_calibration_is_absorbed_by_training_intercepts(synthetic_arcs):
    points = model.geographic([[0, 0], [-7.5, 5]])
    observation = [arc.frequency_hz for arc in synthetic_arcs]
    c0 = model.scores(points, synthetic_arcs, observation)
    fitted_c = model.scores(points, synthetic_arcs, observation, calibration_hz=8e4)
    np.testing.assert_allclose(c0, fitted_c, atol=1e-10)
    assert c0[0][1] < 1e-9
    assert c0[1][1] < 1e-9


def test_holdout_cannot_move_training_fit(synthetic_arcs):
    before = model.fit(synthetic_arcs, 0, "curve", 0)
    damaged = []
    for arc in synthetic_arcs:
        wrong = arc.frequency_hz.copy()
        wrong[len(wrong) * 3 // 5 :] += 6000
        damaged.append(model.Arc(arc.times_s, wrong, arc.position_km, arc.velocity_km_s))
    after = model.fit(damaged, 0, "curve", 0)
    assert after["arms"]["c0"]["forced_latlon"] == before["arms"]["c0"]["forced_latlon"]
    assert before["arms"]["c0"]["forced_latlon"] == model.geographic([-7.5, 5]).tolist()
    assert before["metrics"]["held_rms_hz"] < 1e-9
    assert after["metrics"]["held_rms_hz"] == pytest.approx(6000)


def test_region_face_and_single_track_withheld(synthetic_arcs):
    outside = model.fit(synthetic_arcs, 12.5, "curve", 0)
    assert outside["reason"] == "fit_at_region_face"
    assert outside["arms"]["c0"]["latlon"] is None
    assert outside["arms"]["c0"]["forced_latlon"] is not None
    single = model.fit(synthetic_arcs[:1], 0, "curve", 0)
    assert single["reason"] == "fewer_than_two_author_tracks"
    assert model.fit(synthetic_arcs, 0, "center", 0)["arms"]["c0"]["latlon"] == list(model.CITY)
    shuffled = model.fit(synthetic_arcs, 0, "time-shuffle", 0)
    assert shuffled["metrics"]["held_rms_hz"] > 10_000


def test_source_members_exclude_hidden_metadata(tmp_path):
    with ZipFile(tmp_path / "sample.zip", "w") as archive:
        for name in ("__MACOSX/foo.mat", "Outputs/._red.mat", "Outputs/", "Outputs/red.mat"):
            archive.writestr(name, b"")
        assert [str(path) for path in trial.members(archive)] == ["Outputs/red.mat"]
    assert (
        trial.timestamp("file_10-56-41_24-04-2026.mat").isoformat() == "2026-04-24T10:56:41+00:00"
    )
    with pytest.raises(ValueError, match="no explicit acquisition start"):
        trial.timestamp("undated.mat")


def test_display_reports_no_identified_rf_fit_or_duplicate_center(synthetic_arcs):
    original = model.fit(synthetic_arcs, 0, "curve", 0)
    shown = results.display_row(dict(result=original, method="curve"))["result"]["arms"]
    assert shown["fitted_c"]["status"] == "unavailable"
    assert shown["fitted_c"]["forced_latlon"] is None
    assert shown["c0"] == original["arms"]["c0"]
    assert original["arms"]["fitted_c"] == original["arms"]["c0"]
    center = model.fit(synthetic_arcs, 0, "center", 0)
    shown = results.display_row(dict(result=center, method="center"))["result"]["arms"]
    assert shown["fitted_c"] == shown["c0"] == {"latlon": list(model.CITY)}
