from io import BytesIO

import numpy as np
from scipy.io import savemat
from scipy.spatial import cKDTree

from tools.pipeline_eval.qualification.field_anonymous_trial import from_mat
from tools.pipeline_eval.variants import field_anonymous_doppler as solver


def test_cancellation_and_clock_forecast_do_not_fit_held_levels():
    t = 15 + np.arange(solver.SAMPLES, dtype=float)
    f = t**2
    measured = f + 970.0 + 6 * t
    np.testing.assert_allclose(solver.differences(measured, f, t, 6.0), 0.0, atol=1e-9)
    # The single-band calibration adds an arbitrary constant. It vanishes on both folds.
    a = solver.differences(measured + 5732.4, f, t, 6.0)
    np.testing.assert_allclose(a, 0.0, atol=1e-9)
    measured[solver.EARLY :] += 250
    a = solver.differences(measured, f, t, 6.0)
    np.testing.assert_allclose(a[: solver.EARLY], 0.0, atol=1e-9)
    np.testing.assert_allclose(a[solver.EARLY :], 250.0, atol=1e-9)


def test_anonymous_shared_drift_picks_planted_site_and_orbits():
    coordinates = np.array([[0.0, 0.0], [0.3, 0.3], [0.0, -0.5]])
    xyz, _ = solver.geometry(coordinates)
    times = np.arange(solver.SAMPLES, dtype=float) * 2
    p0 = np.array([[6950, -40, 30], [6780, 100, -400], [6840, -110, 270]])
    velocity = np.array([[0.01, 6.1, 3.9], [0.12, -3.0, 7.1], [-0.08, -6.0, -4.4]])
    p = p0[:, None, :] + times[None, :, None] * velocity[:, None, :]
    v = np.broadcast_to(velocity[:, None, :], p.shape).copy()
    sky_points = p[:, solver.EARLY // 2]
    sky = cKDTree(sky_points / np.linalg.norm(sky_points, axis=1)[:, None])
    los = p - xyz[0]
    doppler = (
        -solver.RF_HZ / solver.LIGHT_KM_S * np.sum(v * los, axis=2) / np.linalg.norm(los, axis=2)
    )
    tracks = [
        solver.Arc(times + 100 * i, f + 600 * i + 6 * times, p, v, np.arange(21, 24), sky, 0.5)
        for i, f in enumerate(doppler)
    ]
    rows = solver.evaluate(tracks, coordinates, [0, 1, 2], solver.DRIFTS_HZ_S)
    best = min(rows, key=lambda row: row["early"])
    assert best["label"] == 0
    assert best["drift"] == 6
    assert best["ids"] == [21, 22, 23]
    assert best["held"] < 1e-15
    assert min(row["early"] for row in rows if row["label"] != 0) > best["early"]


def test_receiver_preserves_rival_and_withholds_when_held_position_is_ambiguous():
    points = np.array([[0.0, 0.0], [0, 0.06], [0.5, 0.1]])
    xyz, _ = solver.geometry(points)
    rows = [
        dict(
            point=point,
            xyz=site,
            label=i,
            early=10 + i,
            held=loss,
            ids=[1, 2, 3],
            supported=[0, 1, 2],
            held_supported_rms_hz=10.0,
            drift=0.0,
            edge_km=2.0,
        )
        for i, ((point, site), loss) in enumerate(
            zip(zip(points, xyz, strict=True), (100.0, 75.0, 25_000.0), strict=True)
        )
    ]
    arcs = [type("Window", (), {"times": np.arange(solver.SAMPLES) + 20 * i}) for i in range(3)]
    r = solver.summarize(rows, arcs, points.tolist(), null=25_000)
    assert r["status"] == "withheld"
    assert r["reason"] == "weak_held_spatial_margin"
    assert r["metrics"]["spatial_margin_hz2"] == -25.0
    assert r["arms"]["c0"] == r["arms"]["fitted_c"]
    assert r["arms"]["c0"]["forced_latlon"] == [0.0, 0.0]
    rows[1]["held"] = 25_000.0
    assert solver.summarize(rows, arcs, points.tolist(), null=25_000)["status"] == "ok"
    rows[0]["ids"] = [1, 1, 3]
    assert solver.summarize(rows, arcs, points.tolist(), null=25_000)["reason"] == (
        "insufficient_independent_held_arcs"
    )


def test_global_lattice_is_fixed_and_covers_both_hemispheres():
    a, b = solver.world_lattice(), solver.world_lattice()
    np.testing.assert_array_equal(a, b)
    assert len(a) > 350
    assert a[:, 0].max() == -a[:, 0].min() == 85
    assert len(np.unique(a, axis=0)) == len(a)
    np.testing.assert_allclose(solver.offset([89, 179.5], np.array([[0.0, 0.0]])), [[89, 179.5]])


def test_decoder_reads_only_measured_columns_and_not_author_id():
    times = np.arange(30.0)
    movie = np.empty((1, 1), dtype=object)
    movie[0, 0] = np.column_stack((times, -91 * times, np.full(30, np.nan)))
    enriched = BytesIO()
    savemat(enriched, dict(main_tone_dict=movie, id_dict=["location-assisted ID"]))
    initial = BytesIO()
    savemat(initial, dict(main_tone_dict=movie))
    arcs, count, dropped = from_mat(enriched.getvalue())
    assert (arcs, count, dropped) == from_mat(initial.getvalue())
    assert len(arcs) == 1 and set(arcs[0]) == {"times", "values"}
    assert len(arcs[0]["times"]) == solver.SAMPLES
