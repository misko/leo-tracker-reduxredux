from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3 import accepted_lean_clocks, accepted_lean_reuse


HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"


@pytest.fixture
def operands():
    with (HERE / "measurements/accepted-lean-small-operands.json").open() as source:
        row = json.load(source)
    return (np.array(row["times"]), np.array(row["values"]),
            1 / np.array(row["inverse_sigma"]), row["rf_ratio"])


@pytest.fixture
def ports(monkeypatch):
    monkeypatch.syspath_prepend(str(HERE))
    import blind_joint_finish
    import certified_salvage

    return blind_joint_finish, certified_salvage


@pytest.mark.parametrize("rejected", (False, True))
def test_original_seed_gate_reuses_only_unchanged_full_support(monkeypatch, ports, operands, rejected):
    finish, _ = ports
    kernel = finish.conservative_recovery
    original = finish.propose
    original_metrics = kernel.retained_metrics
    t, y, _, q = operands
    n = len(t)
    names = ("a", "b")
    sections = [slice(0, n), slice(n, 2*n)]
    rows = [dict(component=name, candidate_norad=j+1, candidate_index=j) for j, name in enumerate(names)]
    tracks = [dict(key=name, times=t, values=y, observation_ids=[f"{name}.{i}" for i in range(n)],
                   rf_hz=11.5e9*q, receiver=j+1, channel=1) for j, name in enumerate(names)]
    scan = SimpleNamespace(tracks=tracks, hardware=lambda *_: np.zeros(n), rx_basis=[np.zeros((n, 1))]*2)
    node, region, point = {}, SimpleNamespace(half_width_km=10.), np.zeros(2)
    calls = Counter()

    def build(_scan, _node, keep, _point, _reference, _model):
        calls["build"] += 1
        r = np.random.default_rng(3).normal(0., 10., 2*n)
        if rejected:
            r[sections[1]] += 1000.
        ready = SimpleNamespace(
            scan=scan, members=[0, 1], slices=sections, rows=rows, alias=(0, 0), supported=[],
            keep=np.ones(2*n, bool) if keep is None else keep, reference=point,
            state=lambda _: dict(beta=np.zeros(1), smooth=[np.zeros(1)]*2),
            calculate=lambda _: dict(conditional_residual_hz=r),
            conditional_frequency=lambda _: (np.tile(y/q, 2), np.ones(2*n)),
        )
        return ready, np.ones(2), np.zeros(2)

    def metrics(base, xy):
        calls["metrics"] += 1
        return original_metrics(base, xy)

    def entries(_base, _point, gates):
        calls["predictive"] += 1
        assert gates["accepted_points"] == (n if rejected else 2*n)
        return []

    def arm(_scan, _node, keep, name, *_):
        calls[name] += 1
        return dict(owner_rows=[oid for tr, sec in zip(tracks, sections, strict=True)
                                for oid in np.asarray(tr["observation_ids"])[keep[sec]]])

    def isolate(_scan, _node, body, initial, expanded, checked, *_args, **_kwargs):
        calls["isolate"] += 1
        assert np.array_equal(body[0].keep, expanded)
        assert np.array_equal(initial, checked)
        return None

    monkeypatch.setattr(finish.v5_core, "scan_context", lambda *_: scan)
    monkeypatch.setattr(finish, "history_model", lambda *_: ({}, True))
    monkeypatch.setattr(finish, "build_at", build)
    monkeypatch.setattr(kernel, "retained_metrics", metrics)
    monkeypatch.setattr(kernel, "salvage", lambda _scan, node, keep: (node, keep, []))
    monkeypatch.setattr(finish, "select_entries", entries)
    monkeypatch.setattr(finish, "arm_finish", arm)
    monkeypatch.setattr(finish, "readout", lambda value: value)
    monkeypatch.setattr(finish, "pair_passes", lambda *_a, **_kw: True)
    args = dict(status="inputs_prepared", noise={}), region, None
    cold = dict(cold_start=lambda *_: (node, point, {}, {}), rescue=isolate)

    expected_audit = {}
    expected, error = original(*args, expected_audit, **cold)
    assert error is None
    original_calls = calls.copy()
    calls.clear()
    changed_audit, reuse = {}, Counter()
    with accepted_lean_reuse.binding(reuse):
        actual, error = finish.propose(*args, changed_audit, **cold)
    assert error is None and finish.propose is original
    assert actual["arms"] == expected["arms"]
    assert changed_audit["support"] == expected_audit["support"]
    assert changed_audit["support"]["initial_curved"] == (n if rejected else 2*n)
    assert reuse["unchanged_seed_gates_reused"] == (0 if rejected else 1)
    for name in ("build", "metrics"):
        assert calls[name] == original_calls[name] - reuse["unchanged_seed_gates_reused"]
    assert {k: calls[k] for k in ("c0", "fitted_c", "predictive", "isolate")} == dict(
        c0=1, fitted_c=1, predictive=1, isolate=1)


def test_fine_retention_reuses_exact_profile_operands_and_order(monkeypatch, ports, operands):
    _, salvage = ports
    t, y, noise, rf = operands
    n = len(y)
    original_fine = salvage.fine_alternatives
    profiles, mats = [], []
    actual_profile = salvage.likelihood.profile

    def profile(observed, predicted, matrix):
        terms = actual_profile(observed, predicted, matrix)
        profiles.append((matrix.copy(), {name: a.tobytes() for name, a in terms.items()}))
        mats.append(matrix)
        return terms

    monkeypatch.setattr(salvage.likelihood, "profile", profile)
    # Keep one whole pass and two overlapping slices. Vary the forecasts and
    # hold the recorded observations and original per-observation noise fixed.
    def frequency(bank, times, labels, phases, *_):
        row = int(bank["position_km"][0, 0, 0])
        f = np.tile((y + row*np.sin(t)) / rf, len(phases))
        return f, np.full(len(f), 20. if row < 4 else -20.)

    k = SimpleNamespace(selected_supports=lambda _: [(0, n), (0, n-1), (1, n)],
                        raw_curvature=lambda _: True, profile=profile, paired_phase_frequency=frequency,
                        batch_noise_screen=lambda r, _: {"noise_screen_pass": np.ones(len(r), bool)})
    sky = dict(time_s=t, position_km=np.arange(5.)[:, None, None], velocity_km_s=np.zeros((5, 1, 1)))
    scan = SimpleNamespace(sky=sky, norads=np.arange(71, 76))
    arguments = k, scan, dict(times=t, values=y), y, noise, rf, {4, 2, 3, 0, 1}, (0., 0.)
    replay = lambda *_: pytest.fail("Unexpected original fine fallback")
    ordinary, candidate = Counter(), Counter()
    expected = original_fine(replay, ordinary, *arguments)
    original_profiles = list(profiles)
    assert len({id(w) for w in mats}) == ordinary["profile_calls"]
    profiles.clear()
    mats.clear()
    audit = Counter()
    with accepted_lean_reuse.binding(audit):
        actual = salvage.fine_alternatives(replay, candidate, *arguments)
    assert actual == expected and salvage.fine_alternatives is original_fine
    assert [row["candidate_index"] for row in actual[0][:4]] == [0, 1, 2, 3]
    assert len(profiles) == len(original_profiles) == 12
    for (left, lhs_terms), (right, rhs_terms) in zip(profiles, original_profiles, strict=True):
        assert left.tobytes() == right.tobytes()
        assert lhs_terms == rhs_terms
    assert audit["whitening_reuses"] == 9
    assert audit["whitening_builds"] == len({id(w) for w in mats}) == 3


def test_unsupported_fine_profile_uses_original_fallback(monkeypatch, ports, operands):
    _, salvage = ports
    t, y, noise, rf = operands
    guarded = SimpleNamespace(selected_supports=lambda _: [(0, len(t))],
                              raw_curvature=lambda _: True, profile=lambda *_: None)
    audit, counts = Counter(), Counter()
    with accepted_lean_reuse.binding(audit):
        assert salvage.fine_alternatives(
            lambda *_: (["original"], 1), counts, guarded, None, dict(times=t, values=y),
            y, noise, rf, {0}, (0., 0.)) == (["original"], 1)
    assert counts["fine_replays"] == 1
    assert not audit


def test_partition_excludes_rank_already_inside_cold_and_has_no_finalist_wall():
    clock = lambda value: dict(cpu_s=value, elapsed_s=value)
    cold = dict(prefix=[dict(cpu_ns=100_000_000)], completed=[dict(cpu_ns=200_000_000)])
    attempt = dict(
        cold=cold, cold_clocks=clock(1.), candidate_pre_evidence_clocks=clock(3.),
        sensitive_confidence=[dict(clocks=clock(.4))],
        initial_gate_clocks=clock(.5), predictive_clocks=clock(.25),
        provisional_salvage=dict(status="reverted", seed_gate_clocks=clock(.45), isolation_clocks=clock(.1)),
    )
    risk = dict(two_centre_rank=dict(paid=dict(cpu_ns=600_000_000, elapsed_ns=600_000_000)))
    stages, nested = accepted_lean_clocks.partition(attempt, risk)
    assert stages["elapsed_s"]["other"] == pytest.approx(.7)
    assert stages["elapsed_s"]["cold"] == 1.
    assert nested["cpu_s"]["cold"]["other"] == pytest.approx(.1)
    assert "finalist_prefix" not in nested["elapsed_s"]["cold"]
    assert nested["cpu_s"]["sensitive_confidence"] == .4

    attempt["provisional_salvage"]["predictive_and_pair_clocks"] = clock(.1)
    with pytest.raises(ValueError, match="nesting"):
        accepted_lean_clocks.partition(attempt, risk)
