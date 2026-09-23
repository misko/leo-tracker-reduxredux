import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "reports/2026_09_23_train_orbit_uncertainty_design/run_pilot.py"
SPEC = importlib.util.spec_from_file_location("train_orbit_uncertainty_pilot", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_disk_parameterization_stays_strictly_inside_radius():
    for raw in (np.array([0.0, 0.0]), np.array([3.0, 4.0]), np.array([1e6, -1e6])):
        assert np.linalg.norm(MODULE.disk_point(raw, 250.0)) < 250.0


def test_target_point_excludes_post_cutoff_history():
    hour = MODULE.NS_HOUR
    current = "current"
    records = [
        {"text": "old", "epoch_utc_ns": 10 * hour, "first_collected_utc_ns": 11 * hour},
        {"text": current, "epoch_utc_ns": 20 * hour, "first_collected_utc_ns": 21 * hour},
        {"text": "future", "epoch_utc_ns": 30 * hour, "first_collected_utc_ns": 31 * hour},
    ]
    satellite = SimpleNamespace(bstar=0.0, no_kozai=1.0, ecco=0.01)
    study = SimpleNamespace(
        tle_key=lambda text: text,
        phase_seconds=lambda *_args: 2.0,
        predict_rate=lambda _model, recent, _feature: recent,
    )
    original = MODULE.parse_element_sets
    MODULE.parse_element_sets = lambda _text: SimpleNamespace(satellites=[satellite])
    try:
        phase, detail = MODULE.target_point_phase(study, current, records, 25 * hour, 30 * hour, {})
    finally:
        MODULE.parse_element_sets = original
    expected_rate = 2.0 / 10
    assert detail["previous_epoch_utc_ns"] == 10 * hour
    assert phase == expected_rate * 10
