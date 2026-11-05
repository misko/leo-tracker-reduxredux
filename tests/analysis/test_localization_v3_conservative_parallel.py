import hashlib
from pathlib import Path
from types import SimpleNamespace

import algo07v3_preconservative_arms_oracle as oracle
import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import conservative_recovery as policy
from leo.operations.localization_v3_parallel import ParallelFitFailure, map_initial_arms


def test_conservative_oracle_is_original_source():
    assert hashlib.sha256(Path(oracle.__file__).read_bytes()).hexdigest() == (
        '1980c199bb2a195e06e11d5bd4ebc56cf00ea30ee7c65bcaa21d17bc16544d5b')


def fake_models(monkeypatch, scenario):
    rows = [dict(component=k) for k in ('a', 'b', 'c')]
    slices = [slice(i * 4, (i + 1) * 4) for i in range(3)]

    def problem(scan, node, sigma, fitted_c, *, reference, keep):
        return SimpleNamespace(rows=rows, slices=slices, keep=keep.copy(),
                               reference=reference, fitted_c=fitted_c,
                               unpicklable=lambda: None)

    def fit(scan, node, keep, arm, **budgets):
        assert budgets == dict(rounds=3, iterations=7)
        if scenario == 'failure' and arm == 'fitted_c':
            raise RuntimeError('fit failed')
        reference = np.array([int(arm == 'fitted_c') / 10])
        p = problem(scan, node, scan.radio_sigma_hz, arm == 'fitted_c',
                    reference=reference, keep=keep)
        p.phase_sigma = np.array([2.])
        record = dict(fit=dict(parameters=np.array([float(keep.sum()), 0.])),
                      phase_reference=reference, phase_widths_s=p.phase_sigma)
        return p, record

    def metrics(p, x):
        bad = ({'a', 'b', 'c'} if scenario == 'all_rejected' else
               ({'b'} if p.fitted_c else {'a'}) if scenario == 'rejection' else set())
        return dict(tracks=[dict(row, compatible=row['component'] not in bad)
                            for row, sl in zip(rows, slices, strict=True) if p.keep[sl].any()])

    for module in (oracle, policy):
        monkeypatch.setattr(module, 'causal_fit', fit)
        monkeypatch.setattr(module, 'retained_metrics', metrics)
        monkeypatch.setattr(module, 'PositionNormal', problem)
    return SimpleNamespace(radio_sigma_hz=75.)


@pytest.mark.parametrize('scenario,limit', [
    ('stable', 4), ('rejection', 4), ('rejection', 1), ('all_rejected', 4)])
def test_forked_compact_records_preserve_serial_masks_history_and_callbacks(
        monkeypatch, scenario, limit):
    scan = fake_models(monkeypatch, scenario)
    mask = np.ones(12, bool)
    reference_events, candidate_events = [], []
    kw = dict(max_rounds=limit, rounds=3, iterations=7)
    expected = oracle.fit_and_gate(scan, {}, mask, 'gate', **kw,
                                   on_round=lambda *args: reference_events.append(args))
    actual = policy.fit_and_gate(scan, {}, mask, 'gate', **kw, map_arms=map_initial_arms,
                                 on_round=lambda *args: candidate_events.append(args))
    assert fingerprint(actual[1:]) == fingerprint(expected[1:])
    assert fingerprint(candidate_events) == fingerprint(reference_events)
    assert mask.all()
    for key in ('rows', 'slices', 'keep', 'reference', 'phase_sigma', 'fitted_c'):
        if key == 'slices':
            assert actual[0].slices == expected[0].slices
        else:
            assert fingerprint(getattr(actual[0], key)) == fingerprint(getattr(expected[0], key))


def test_child_failure_does_not_become_rejection_or_emit_completed_round(monkeypatch):
    scan = fake_models(monkeypatch, 'failure')
    events = []
    with pytest.raises(ParallelFitFailure, match='fit failed'):
        policy.fit_and_gate(scan, {}, np.ones(12, bool), 'gate', rounds=3, iterations=7,
                            map_arms=map_initial_arms, on_round=lambda *args: events.append(args))
    assert not events
