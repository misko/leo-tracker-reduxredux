import importlib.util
from pathlib import Path
import sys

import pytest


PATH = Path(__file__).with_name("calibration_consistent_fit.py")
SPEC = importlib.util.spec_from_file_location("calibration_consistent_fit", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def row(track, observation, east, matched=True, ratio=0.2):
    return {"session_id": "s", "split": "cal", "track_id": track,
            "observation_id": observation, "receiver_id": "rx0",
            "channel": 1, "edge": "lower", "sample_rate_hz": 1,
            "anchor_margin": 2., "matched": matched,
            "log_margin_ratio_rx1_rx0": ratio if matched else None,
            "east": east, "up": 0.5}


def test_exact_join_replaces_only_direction():
    rows = [row("a", "1", .1), row("b", "2", .2)]
    directions = [
        {"session_id": "s", "track_id": "b", "observation_id": "2",
         "robust_mean_east": -.8, "robust_mean_up": .1},
        {"session_id": "s", "track_id": "a", "observation_id": "1",
         "robust_mean_east": -.7, "robust_mean_up": .2},
    ]
    result = MODULE.replace_directions(rows, directions)
    assert [(x["east"], x["up"]) for x in result] == [(-.7, .2), (-.8, .1)]
    assert result[0]["matched"] is rows[0]["matched"]
    assert rows[0]["east"] == .1


@pytest.mark.parametrize("directions", [
    [],
    [{"session_id": "s", "track_id": "a", "observation_id": "1",
      "robust_mean_east": 0., "robust_mean_up": 0.},
     {"session_id": "s", "track_id": "a", "observation_id": "1",
      "robust_mean_east": 0., "robust_mean_up": 0.}],
])
def test_join_rejects_missing_or_duplicate(directions):
    with pytest.raises(ValueError):
        MODULE.replace_directions([row("a", "1", .1)], directions)


def test_m0_fit_and_variance_ignore_direction_changes():
    rows = [row("a", "1", -.8, True, -.2), row("a", "2", -.2, True, .3),
            row("b", "3", .2, True, .5), row("b", "4", .8, False, None)]
    changed = [dict(value, east=value["east"] * -7, up=-99.) for value in rows]
    old = MODULE.fit_bundle(rows)
    new = MODULE.fit_bundle(changed)
    assert old["detection"]["M0"] == new["detection"]["M0"]
    assert old["ratio"]["M0"] == new["ratio"]["M0"]
    assert old["ratio_variance"]["M0"] == new["ratio_variance"]["M0"]
