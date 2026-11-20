"""Request-time curvature and archived-endpoint selection."""

import ast
from shutil import copyfile

import numpy as np
import pytest

from tools.pipeline_eval.qualification import late_routing_sources as measured
from tools.pipeline_eval.qualification.late_routing_results import (
    ARCHIVE_METHOD,
    archive_rows,
)
from tools.pipeline_eval.variants.late_routing import ARMS, evaluate


def target():
    times = np.linspace(0, 32, 33)
    signal = 1200 + 40 * times + 11 * times**2
    return dict(times_s=times, corrected_hz={"c0": signal, "fitted_c": signal - 40})


def test_curvature_predicts_both_calibration_arms():
    trace = target()
    decision = evaluate([trace])
    assert decision["run"]
    assert decision["targets"][0]["training_points"] == 17
    assert all(decision["targets"][0]["arms"][arm]["held_ratio"] < 0.01 for arm in ARMS)
    trace["corrected_hz"]["fitted_c"] = -trace["corrected_hz"]["fitted_c"]
    assert not evaluate([trace])["run"]


def test_extrapolation_rejects_misleading_training_curvature_and_missing_ends():
    trace = target()
    for arm in ARMS:
        trace["corrected_hz"][arm][-8:] += 12000
    assert not evaluate([trace])["run"]
    trace = target()
    indices = np.r_[0, 8:31]
    trace["times_s"] = trace["times_s"][indices]
    trace["corrected_hz"] = {k: v[indices] for k, v in trace["corrected_hz"].items()}
    assert evaluate([trace])["targets"][0]["arms"] == {}
    assert not evaluate([])["run"]


def test_invalid_predecision_packet_is_not_a_negative_decision():
    with pytest.raises(ValueError, match="at most three"):
        evaluate([target()] * 4)
    trace = target()
    trace["times_s"][6] = trace["times_s"][5]
    with pytest.raises(ValueError, match="time axis"):
        evaluate([trace])


@pytest.mark.parametrize("run", (True, False))
def test_archived_comparison_uses_only_the_two_authenticated_endpoints(run):
    first = dict(x=[1, 2], latlon=[37.0, -122.0], rf_rms_hz=100)
    last = dict(x=[2, 2], latlon=[37.1, -122.0], rf_rms_hz=70)
    data = dict(id="fixture", native_sha256="native", catalog_sha256="catalog", tile={}, samples=[])
    data.update(request_sha256="request", archive_sha256="archive", route=dict(run=run, targets=[]))
    oracle = dict(stages={a: dict(cavity=first, incumbent=first, final=last) for a in ARMS})
    records, positions = archive_rows(data, oracle, [37.0, -122.0], {a: last for a in ARMS})
    selected = next(row for row in positions if row["method"] == ARCHIVE_METHOD)
    for arm in ARMS:
        actual = selected["result"]["arms"][arm]
        source = last if run else first
        assert actual == {k: source[k] for k in ("latlon", "rf_rms_hz")}
    assert all(row["dispatch"] is run for row in records)


def test_all_recorded_gates_replay_from_a_relocated_receipt(tmp_path):
    for name in (
        "PROTOCOL.md",
        "run-lock.json",
        "bypass-lock.json",
        measured.BLIND_LOCK,
        measured.BLIND,
        measured.ZIP,
    ):
        copyfile(measured.REPORT / name, tmp_path / name)
    assert measured.verify_gates(tmp_path) == {"cases": 135, "routed": 127, "bypassed": 8}
    (tmp_path / "PROTOCOL.md").write_text("changed")
    with pytest.raises(ValueError, match="protocol differs"):
        measured.measured_sources(tmp_path)


def _function(source, name):
    return next(node for node in ast.parse(source).body if getattr(node, "name", None) == name)


def test_worker_import_order_and_extractor_layout_preserve_science():
    exact = measured.measured_sources(measured.REPORT)
    for relative, name in ((measured.WORKER, "worker"), (measured.EXTRACTOR, "extract")):
        old = _function(exact[relative], name)
        cleaned = _function((measured.ROOT / relative).read_bytes(), name)
        if relative == measured.WORKER:
            for function in (old, cleaned):
                assert all(isinstance(node, ast.ImportFrom) for node in function.body[:2])
                function.body[:2] = sorted(function.body[:2], key=ast.dump)
        assert ast.dump(old) == ast.dump(cleaned)

    archival_worker = measured.measured_worker(exact)
    archival_gate = archival_worker.__globals__["late_routing"].evaluate
    assert archival_gate.__code__.co_filename == measured.GATE
    assert archival_gate is not evaluate
    assert archival_gate([target()]) == evaluate([target()])
