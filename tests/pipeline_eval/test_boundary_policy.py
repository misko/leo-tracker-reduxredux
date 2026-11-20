import json
import subprocess
import sys

import pytest

from tools.pipeline_eval.qualification import boundary_policy_trial as trial
from tools.pipeline_eval.variants import compact_tile_decision, compact_tile_interior

TILE = {"center": [40.0, -75.0], "width_km": 25.0}
CLI = [sys.executable, "-B", "-m", "tools.pipeline_eval.variants.compact_tile_decision"]


def output(margin):
    return (
        json.dumps(
            dict(
                status="ok",
                boundary="installed compact",
                metrics={"observations": 77},
                arms={
                    "c0": {"latlon": [40.0, -75.0], "rf_rms_hz": 44.125},
                    "fitted_c": {"latlon": [40 + (12.5 - margin) / 111, -75.0], "rf_rms_hz": 43.5},
                },
            ),
            indent=1,
        ).encode()
        + b" \n"
    )


def test_public_flag_off_is_exact_and_optional_guard_preserves_both_selected_positions():
    raw = output(0.019)
    original = subprocess.run(CLI, input=raw, capture_output=True, check=True).stdout
    assert original == raw
    guarded = json.loads(
        subprocess.run(
            CLI + ["--interior-guard", "--tile", "40", "-75"],
            input=raw,
            capture_output=True,
            check=True,
        ).stdout
    )
    assert guarded == compact_tile_interior.guard(json.loads(raw), TILE)
    assert guarded["status"] == "withheld" and all(
        a["latlon"] is None for a in guarded["arms"].values()
    )
    for name, arm in json.loads(raw)["arms"].items():
        assert guarded["arms"][name]["forced_latlon"] == arm["latlon"]
        assert guarded["arms"][name]["rf_rms_hz"] == arm["rf_rms_hz"]


def test_guard_keeps_two_points_beyond_secant_stop_scale_and_leaves_no_estimate_alone():
    raw = output(0.021)
    result = json.loads(compact_tile_decision.decide(raw, enabled=True, tile=TILE))
    assert result["status"] == "ok" and result["arms"] == json.loads(raw)["arms"]
    missing = b'{"status":"timed_out", "reason":"clock", "arms":{}, "metrics":{}}\n'
    assert compact_tile_decision.decide(missing, enabled=True, tile=TILE) == missing


@pytest.mark.parametrize("archived_offset", [(0.12, 0.0), (0.0, -0.14)])
def test_fresh_offers_straddle_one_face_in_exact_receiver_coordinates(archived_offset):
    point = [33.0, 138.0]
    lat, lon = archived_offset
    controls = trial.mapped_offers(point, {"omitted": [point[0] + lat, point[1] + lon]})
    margins = {
        name: compact_tile_interior.margin(point, dict(center=center, width_km=25.0))
        for name, center in controls.items()
    }
    assert margins == pytest.approx(
        dict(center=9.5, **{"near-inside": 1.5, "near-outside": -1.5, "far-omission": -27.5})
    )


def test_resource_monitor_encloses_python_inside_bubblewrap(monkeypatch):
    command = ["time", "taskset", "-c", "14", "bwrap", "--", sys.executable, "-IB", "installed"]
    monkeypatch.setattr(trial.earlier, "isolated", lambda *_: command)
    wrapped = trial.timed_command(None, None, None, None, 14)
    assert wrapped.index("bwrap") < wrapped.index("/usr/bin/time") < wrapped.index(sys.executable)
