import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools/research/refine_joint_receive_clock.py"
SPEC = importlib.util.spec_from_file_location("refine_joint_receive_clock", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_clock_nodes_include_asymmetric_bounds_and_zero():
    nodes = MODULE.clock_nodes(-0.18, 0.17)
    np.testing.assert_allclose(nodes, [-0.18, -0.09, 0, 0.085, 0.17])


def test_lagrange_weights_recover_quartic_and_reject_outside_bound():
    nodes = MODULE.clock_nodes(-0.2, 0.15)
    values = nodes**4 - 2 * nodes**2 + 3 * nodes + 1
    for point in (-0.2, -0.13, 0, 0.11, 0.15):
        expected = point**4 - 2 * point**2 + 3 * point + 1
        assert MODULE.lagrange_weights(nodes, point) @ values == pytest.approx(expected)
    with pytest.raises(ValueError, match="hard bracket"):
        MODULE.lagrange_weights(nodes, 0.16)


def test_state_cache_preserves_clock_sign_and_zero_exactly():
    nodes = MODULE.clock_nodes(-0.2, 0.15)
    states = []
    for value in nodes:
        p = np.full((2, 3, 3), 7_000 + 5 * value + value**2)
        v = np.full((2, 3, 3), 4 - 2 * value + value**3)
        states.append((p, v))
    cache = MODULE.StateCache.build(nodes, states)
    p0, v0 = cache.at(0)
    np.testing.assert_array_equal(p0, states[2][0])
    np.testing.assert_array_equal(v0, states[2][1])
    minus, _ = cache.at(-0.1)
    plus, _ = cache.at(0.1)
    assert np.all(minus < plus)


def test_visibility_and_exact_gate_fail_closed():
    receiver = np.array([6378.0, 0.0, 0.0])
    up = np.array([1.0, 0.0, 0.0])
    position = np.array([[[7000.0, 0.0, 0.0], [6200.0, 0.0, 0.0]]])
    visible = MODULE.visibility_mask(position, receiver, up, np.array([True, False]), -1)
    assert visible.tolist() == [True]
    assert MODULE.qualifies(
        converged=True, maximum_error_hz=0.1, visibility_mismatches=0, score_delta=1e-6
    )
    assert not MODULE.qualifies(
        converged=True, maximum_error_hz=0.1, visibility_mismatches=1, score_delta=0
    )
    assert not MODULE.qualifies(
        converged=True, maximum_error_hz=0.21, visibility_mismatches=0, score_delta=0
    )


def test_run_rejects_mutated_refinement_checksum(tmp_path):
    refinement = tmp_path / "result.json"
    refinement.write_text(json.dumps({"complete": True, "position_truth_used": False}) + "\n")
    refinement.with_name("result.sha256").write_text("0" * 64 + "\n")
    args = SimpleNamespace(
        output=tmp_path / "output",
        refinement=refinement,
        clock_audit=tmp_path / "clock.json",
        evidence=tmp_path,
        position_radius_km=100.0,
        max_evaluations=8,
        budget_seconds=10.0,
        max_rss_kib=1_000_000,
    )
    with pytest.raises(ValueError, match="sealed truth-free"):
        MODULE.run(args)


def test_run_rejects_mutated_clock_audit_digest(tmp_path):
    refinement = tmp_path / "result.json"
    refinement.write_text(json.dumps({"complete": True, "position_truth_used": False}) + "\n")
    import hashlib

    refinement.with_name("result.sha256").write_text(
        hashlib.sha256(refinement.read_bytes()).hexdigest() + "\n"
    )
    audit = tmp_path / "clock.json"
    audit.write_text(json.dumps({"content_digest": "sha256:" + "0" * 64}) + "\n")
    args = SimpleNamespace(
        output=tmp_path / "output",
        refinement=refinement,
        clock_audit=audit,
        evidence=tmp_path,
        position_radius_km=100.0,
        max_evaluations=8,
        budget_seconds=10.0,
        max_rss_kib=1_000_000,
    )
    with pytest.raises(ValueError, match="clock audit content digest"):
        MODULE.run(args)
