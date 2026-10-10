"""Synthetic full193 receipt tests; no radio, reference documents, or fits."""

import hashlib
import json

import pytest

import c_ablation
import evaluation
from test_postseal_preflight import complete_one, prepared, write


def _save_phase(result_dir, label, branch, receipt):
    folder = result_dir / label / branch
    receipt['elapsed_s'] = 1.
    write(folder / 'result.json', receipt)
    slice_name = 'baseline-01' if branch == 'native' else 'candidate-01'
    write(folder / 'slices' / (slice_name + '.done.json'), receipt)


def _final(basin, arm, start):
    zero = arm == 'zero-c'
    return dict(basin=basin, arm=arm, start=start,
                satellites=[100, 200, 300, 400], calibration_penalty=2.,
                fit=dict(converged=True, vector=[0., 0., 0., 0., 0., 0.,
                                                 0. if zero else 7., 0.],
                         objective=10. if zero else 9.,
                         posterior_rms_hz=5. if zero else 3.,
                         signal_windows=100., stationarity=.0001),
                reason=None, seed_audit=dict(effective=[0., 0.]))


def ready(tmp_path, monkeypatch):
    plan, directory = prepared(tmp_path)
    complete_one(plan, directory, tmp_path)
    label = plan['members'][0]['label']
    search_path = directory / label / 'search' / 'result.json'
    search = json.loads(search_path.read_text())
    search['searches'] = {}
    for branch in c_ablation.BRANCHES:
        search['searches'][branch] = dict(regions=[
            dict(east_km=float(index), north_km=float(index + 1))
            for index in range(3)])
        path = directory / label / branch / 'result.json'
        receipt = json.loads(path.read_text())
        receipt['regions'] = {}
        for index in range(3):
            basin = f'point:{float(index)}:{float(index + 1)}'
            receipt['regions'][f'retained-{index}'] = dict(
                calibrations={basin: dict(receiver_baseline_hz=[0.])},
                finals=[_final(basin, arm, start)
                        for arm in c_ablation.ARMS for start in c_ablation.STARTS])
        _save_phase(directory, label, branch, receipt)
    write(search_path, search)
    plan.update(source_sha256={}, evaluation_source_sha256={}, runtime=dict(sha256={}))
    protocol = tmp_path / 'protocol.json'
    write(protocol, plan)
    write(tmp_path / 'evaluation_protocol.json', dict(
        numerical_protocol_digest='d',
        numerical_protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),
        source_sha256={}))
    for name in ('c_ablation.py', 'test_c_ablation.py', 'C_ABLATION_PLAN.md',
                 'postseal_preflight.py'):
        (tmp_path / name).write_text('synthetic ' + name)
    write(tmp_path / 'C_ABLATION_FREEZE.json', dict(
        numerical_protocol_digest='d', source_sha256={
            name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
            for name in c_ablation.FREEZE_FILES}))
    monkeypatch.setattr(c_ablation, 'HERE', tmp_path)
    monkeypatch.setattr(evaluation, 'ROOT', tmp_path)
    return plan, directory


def test_full193_gate_precedes_b1_receipts_and_reference_factory(tmp_path, monkeypatch):
    plan, directory = ready(tmp_path, monkeypatch)
    (directory / 'L192' / 'zero' / 'result.json').unlink()
    calls = []
    monkeypatch.setattr(c_ablation, '_read_bound',
                        lambda *args: calls.append('B1') or None)
    with pytest.raises(FileNotFoundError):
        c_ablation.build(plan, directory, 'd', root=tmp_path,
                         evaluation_factory=lambda *args: calls.append('reference'))
    assert calls == []


def test_successor_freeze_tamper_blocks_preflight_b1_and_reference(tmp_path, monkeypatch):
    plan, directory = ready(tmp_path, monkeypatch)
    (tmp_path / 'C_ABLATION_PLAN.md').write_text('tampered plan')
    calls = []
    monkeypatch.setattr(c_ablation.postseal_preflight, 'preflight',
                        lambda *args, **kwargs: calls.append('preflight'))
    monkeypatch.setattr(c_ablation, '_read_bound',
                        lambda *args: calls.append('B1'))
    with pytest.raises(ValueError, match='successor source changed'):
        c_ablation.build(plan, directory, 'd', root=tmp_path,
                         evaluation_factory=lambda *args: calls.append('reference'))
    assert calls == []


def test_same_region_pairs_and_full_failure_denominator(tmp_path, monkeypatch):
    plan, directory = ready(tmp_path, monkeypatch)
    calls = []
    def factory(_plan, rows):
        calls.append(('factory', len(rows)))
        def evaluate(label, branch, arm, operation):
            calls.append((label, branch, arm, operation['start']))
            return 2. if arm == 'zero-c' else 1.
        return evaluate
    report = c_ablation.build(plan, directory, 'd', root=tmp_path,
                              evaluation_factory=factory)
    assert report['expected_opportunities'] == 3474
    assert report['primary_matched_seed_opportunities'] == 2316
    assert report['arm_specific_continuation_opportunities'] == 1158
    assert report['opportunity_counts'] == {'paired': 18, 'phase-unavailable': 3456}
    assert calls[0] == ('factory', 193) and len(calls) == 37
    pair = report['opportunities'][0]
    assert pair['start_scope'] == 'strict-matched-seed'
    assert pair['frequency']['objective_delta_fitted_minus_zero'] == -1.
    assert pair['frequency']['posterior_rms_hz_delta_fitted_minus_zero'] == -2.
    assert pair['position']['delta_fitted_minus_zero_km'] == -1.
    assert 'operation' not in pair['arms']['zero-c']


def test_bank_mismatch_keeps_failure_without_frequency_or_position(tmp_path, monkeypatch):
    plan, directory = ready(tmp_path, monkeypatch)
    path = directory / 'L0' / 'native' / 'result.json'
    receipt = json.loads(path.read_text())
    receipt['regions']['retained-0']['finals'][3]['satellites'] = [100, 200, 300, 999]
    _save_phase(directory, 'L0', 'native', receipt)
    calls = []
    def factory(*_):
        return lambda *args: calls.append(args) or 1.
    report = c_ablation.build(plan, directory, 'd', root=tmp_path,
                              evaluation_factory=factory)
    assert report['opportunity_counts']['integrity-failure'] == 1
    first = report['opportunities'][0]
    assert first['status'] == 'integrity-failure'
    assert first['frequency'] == {} and first['position'] == {}
    assert len(calls) == 34


def test_missing_and_unqualified_named_starts_are_covered(tmp_path, monkeypatch):
    plan, directory = ready(tmp_path, monkeypatch)
    path = directory / 'L0' / 'native' / 'result.json'
    receipt = json.loads(path.read_text())
    finals = receipt['regions']['retained-0']['finals']
    finals.remove(next(f for f in finals if f['arm'] == 'zero-c'
                       and f['start'] == 'association'))
    next(f for f in finals if f['arm'] == 'fitted-c'
         and f['start'] == 'zero-timing')['fit']['converged'] = False
    _save_phase(directory, 'L0', 'native', receipt)
    report = c_ablation.build(plan, directory, 'd', root=tmp_path,
                              evaluation_factory=lambda *_: lambda *_: 1.)
    assert report['opportunity_counts']['missing-arm'] == 1
    assert report['opportunity_counts']['unqualified'] == 1
    assert report['opportunity_counts']['paired'] == 16


def test_failed_fit_without_seed_audit_is_unqualified_not_integrity_failure(
        tmp_path, monkeypatch):
    plan, directory = ready(tmp_path, monkeypatch)
    path = directory / 'L0' / 'native' / 'result.json'
    receipt = json.loads(path.read_text())
    failed = next(f for f in receipt['regions']['retained-0']['finals']
                  if f['arm'] == 'zero-c' and f['start'] == 'association')
    failed.update(fit=None, reason='synthetic stage failure', seed_audit=None)
    _save_phase(directory, 'L0', 'native', receipt)
    report = c_ablation.build(plan, directory, 'd', root=tmp_path,
                              evaluation_factory=lambda *_: lambda *_: 1.)
    pair = report['opportunities'][0]
    assert pair['status'] == 'unqualified'
    assert pair['arms']['zero-c']['reason'] == 'synthetic stage failure'
    assert pair['frequency'] == {} and pair['position'] == {}
    assert report['opportunity_counts'].get('integrity-failure', 0) == 0


def test_reference_failure_preserves_frequency_pair_and_coverage(tmp_path, monkeypatch):
    plan, directory = ready(tmp_path, monkeypatch)
    def factory(*_):
        def unavailable(*_):
            raise ValueError('synthetic reference absent')
        return unavailable
    report = c_ablation.build(plan, directory, 'd', root=tmp_path,
                              evaluation_factory=factory)
    pair = report['opportunities'][0]
    assert pair['status'] == 'paired'
    assert pair['frequency']['objective_delta_fitted_minus_zero'] == -1.
    assert pair['position']['zero-c']['status'] == 'failed'
    assert 'delta_fitted_minus_zero_km' not in pair['position']
