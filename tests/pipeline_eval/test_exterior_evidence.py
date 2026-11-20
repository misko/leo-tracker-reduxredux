import json
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import exterior_evidence_trial as trial
from tools.pipeline_eval.qualification import exterior_evidence_worker as worker
from tools.pipeline_eval.scoring import ARMS


def smooth(status="ok"):
    point = [37.9, -122.5]
    return dict(
        result=dict(
            status=status,
            reason=None if status == "ok" else "native gate",
            boundary="native smooth",
            metrics={},
            arms={
                arm: dict(
                    latlon=point if status == "ok" else None,
                    forced_latlon=point,
                    region_id="tile",
                    rf_rms_hz=100.0,
                )
                for arm in ARMS
            },
        ),
        method=trial.clock.METHOD,
        observation_sha256="fixed",
        worker_wall_s=4.0,
    )


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("denied", "withheld"),
        ("accepted", "ok"),
        ("timed_out", "timed_out"),
        ("missing", "missing"),
        ("unavailable", "unavailable"),
    ],
)
def test_frozen_evidence_filters_without_replacing_smooth_endpoints(state, expected):
    original = smooth()
    result = trial.combine(original, dict(state=state))
    assert result["result"]["status"] == expected
    assert result["observation_sha256"] == original["observation_sha256"]
    for arm in ARMS:
        out, source = result["result"]["arms"][arm], original["result"]["arms"][arm]
        assert out["rf_rms_hz"] == source["rf_rms_hz"]
        assert out["forced_latlon"] == source["latlon"]
        assert out["latlon"] == (source["latlon"] if expected == "ok" else None)
    assert original["result"]["status"] == "ok"


def test_exterior_gate_cannot_rescue_a_first_pass_withholding():
    result = trial.combine(smooth("withheld"), {"state": "accepted"})
    assert result["result"]["reason"] == "native gate"
    assert result["result"]["status"] == "withheld"


def test_gate_worker_binds_native_and_captures_held_arcs_before_cavity(monkeypatch, tmp_path):
    native = tmp_path / "native.json"
    native.write_text(json.dumps({"clock_anchor": {"before": {"realtime_ns": 50}}}))
    monkeypatch.setattr(worker, "Path", lambda path: native if path == "/input/native" else path)
    arc = SimpleNamespace(
        channel=1,
        scale=1.1,
        time_bin=0,
        train_time=np.array([1.0]),
        train_y=np.array([100.0]),
        held_time=np.array([10.0]),
        held_y=np.array([110.0]),
    )
    monkeypatch.setattr(worker.portable_gate, "make_arcs", lambda _doc: ([arc], {}))

    def test_gate(document, tile, archive, bound, library):
        assert tile == {"center": [30.0, -120.0]}
        assert worker.portable_gate.make_arcs(document)[0] == [arc]
        result = worker.v5_core.infer({"status": "inputs_prepared"}, None, None, {"gate": 1})
        result["metrics"]["geographic_gate"] = {"admitted": True}
        return result

    monkeypatch.setattr(worker.tile_region_empirical, "run", test_gate)
    packet = dict(
        native_sha256=sha256(native.read_bytes()).hexdigest(),
        history=[],
        tile={"center": [30.0, -120.0]},
    )
    report = worker.run(packet)
    assert report["gate"] == {"admitted": True}
    assert len(report["held_arc_sha256"]) == 64
    with pytest.raises(ValueError, match="native factor digest"):
        worker.run(dict(packet, native_sha256="different"))


def test_all_104_archival_offers_match_their_sealed_native_smooth_result():
    queries, rows = trial.prior_cases()
    assert len(queries) == 104
    assert len({q["recording"] for q in queries}) == 26
    assert all(
        trial.clock.bindings(q)["input_sha256"] == rows[q["id"]]["input_sha256"] for q in queries
    )
