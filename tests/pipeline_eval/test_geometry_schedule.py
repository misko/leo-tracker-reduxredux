from hashlib import sha256

import numpy as np

from tools.pipeline_eval.qualification import geometry_schedule_trial as trial
from tools.pipeline_eval.variants import geometry_schedule as model


def test_local_doppler_gradient_matches_center_displacement():
    center = (37.0, -122.0)
    site = model.geodetic_to_ecef_km(*center, 0)
    axes = model.ecef_to_enu_matrix(*center)
    position = site + 500 * axes[2] + 350 * axes[0]
    velocity = 7 * axes[0] + axes[1]
    _, analytic, visible = model.geometry(position, velocity, center)
    assert visible
    shift = 0.0001
    for axis, coordinate in enumerate((1, 0)):
        left = list(center)
        right = list(center)
        left[coordinate] -= shift
        right[coordinate] += shift
        u, _, _ = model.geometry(position, velocity, left)
        v, _, _ = model.geometry(position, velocity, right)
        dx = np.linalg.norm(
            model.geodetic_to_ecef_km(*right, 0) - model.geodetic_to_ecef_km(*left, 0)
        )
        assert np.isclose((v - u) / dx, analytic[axis], atol=1e-6)


def test_projection_zeros_offset_and_drift_and_retains_assignment_uncertainty():
    time = np.arange(10.0)
    x = model.line(time)
    j = np.stack((x @ np.array([[5.0, 1.0], [2.0, -3.0]]), x @ np.eye(2)))
    residual, _ = model.affine_residual(j, x)
    assert np.allclose(residual, 0)
    indices, weights = model.posterior(np.zeros(12))
    assert np.array_equal(indices, np.arange(5))
    assert np.isclose(weights.sum(), 5 / 12)


def test_receiving_block_winners_cannot_change_its_slot_scores():
    t = np.arange(0.0, 301, model.GRID_STEP)
    f = 100 + 130 * t + 0.25 * t**2
    j = np.stack((0.07 * t**2, 0.03 * t**2), axis=1)
    bank = model.Bank(f[None, :], (f + 100)[None, :], j[None, :], t[None, :] >= 0, np.array([5]))
    rate = 10_000_000
    rf = int(model.BASE_RF)

    def capture(alter):
        probes = []
        for i in range(70):
            y = 100 + 130 * i + 0.25 * i**2
            if alter and 30 <= i < 60:
                y += 80_000
            candidate = {
                model.visits.CFO: y,
                model.visits.GATE: True,
                model.visits.RANK: 0,
                model.visits.MARGIN: 0.2,
                "integer_epoch_sample": 10,
                "fractional_epoch_offset_samples": 0.0,
            }
            for rx in range(2):
                probes.append(
                    dict(
                        visit_index=i,
                        receiver_id=rx,
                        actual_rf_hz=rf,
                        valid_start_counter=i * rate,
                        candidates=[candidate],
                    )
                )
        return dict(
            source=dict(probes=probes, sample_rate_hz=rate),
            clock_anchor=dict(sample_counter=0),
            delivery_clocks=[dict(monotonic_ns=i * 10**9) for i in range(70)],
        )

    first, _, _ = model.predict(capture(False), bank, (0.9,))
    changed, _, _ = model.predict(capture(True), bank, (0.9,))
    assert first[30:60] == changed[30:60]
    assert any(r["gain"] > 0 for r in first[30:60])


def test_snapshot_uses_latest_signed_source_available_before_capture(tmp_path):
    folder = tmp_path / "archive" / "space-track"
    folder.mkdir(parents=True)
    snapshots = {}
    for date in (2, 4, 6):
        data = str(date).encode()
        digest = sha256(data).hexdigest()
        name = f"{date}-{digest}.tle"
        snapshots[name] = digest
        (folder / name).write_bytes(data)
    path, collected = trial.snapshot(
        dict(job=dict(tle_root=tmp_path), causal_snapshots=snapshots), 5
    )
    assert collected == 4 and path.read_bytes() == b"4"
