import hashlib

import numpy as np
import pytest

from leo.contracts.digests import canonical_digest
from tools.prototype_streaming_doppler import prepare, spline_nodes


def track():
    t = np.linspace(0, 40, 81)
    return {
        "times_s": t.tolist(),
        "measured_hz": (30000 - 200 * t + 0.7 * t * t).tolist(),
        "training_mask": (np.arange(len(t)) % 3 != 2).tolist(),
    }


def test_spline_reproduces_quadratic_and_ignores_validation_values():
    source = track()
    t, y, fit = spline_nodes(source)
    np.testing.assert_allclose(y, 30000 - 200 * t + 0.7 * t * t, atol=1e-8)
    assert fit["training_rms_hz"] < 1e-8
    source["measured_hz"] = [
        v if m else v + 100000
        for v, m in zip(source["measured_hz"], source["training_mask"], strict=True)
    ]
    tt, yy, changed = spline_nodes(source)
    np.testing.assert_array_equal(tt, t)
    np.testing.assert_array_equal(yy, y)
    assert changed["validation_rms_hz"] > 99999


@pytest.mark.parametrize(
    "problem", ["duplicate_time", "nonfinite", "no_validation", "few_training"]
)
def test_bad_track_is_explicit(problem):
    source = track()
    if problem == "duplicate_time":
        source["times_s"][1] = source["times_s"][0]
    elif problem == "nonfinite":
        source["measured_hz"][0] = float("nan")
    elif problem == "no_validation":
        source["training_mask"] = [True] * 81
    else:
        source["training_mask"] = [True] * 3 + [False] * 78
    with pytest.raises(ValueError):
        spline_nodes(source)


def test_export_excludes_answers_and_checks_capture_binding():
    payload = (
        "0 STARLINK-1008\n"
        "1 44714U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999\n"
        "2 44714  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103\n"
    )
    capture = {"session_id": "test", "timing": {"first_sample_estimate_utc_ns": 1}}
    evidence = {**track(), "track_id": "test", "support_digest": "sha256:" + "0" * 64}
    document = {
        "session_id": "test",
        "input_manifest_sha256": canonical_digest(capture),
        "priors": [
            {
                "name": "sacramento",
                "region": {
                    "altitude_m": 0,
                    "center_latitude_deg": 38.5816,
                    "center_longitude_deg": -121.4944,
                    "radius_km": 250,
                },
                "selected": {"latitude_deg": 37.8},
            }
        ],
        "diagnostics": {
            "snapshot_digest": "sha256:" + hashlib.sha256(payload.encode()).hexdigest(),
            "track_evidence": [evidence],
            "reference_evaluation_only": {"latitude_deg": 37.8},
            "selected_track_scores": {"satellite_id": 44714},
        },
    }
    expected = prepare(document, capture, payload, "sacramento")
    document["priors"][0]["selected"] = {"latitude_deg": -30}
    document["diagnostics"]["reference_evaluation_only"] = {"latitude_deg": -30}
    document["diagnostics"]["selected_track_scores"] = {"satellite_id": 99999}
    assert prepare(document, capture, payload, "sacramento") == expected
    capture["timing"]["first_sample_estimate_utc_ns"] = 2
    with pytest.raises(ValueError, match="binding"):
        prepare(document, capture, payload, "sacramento")
