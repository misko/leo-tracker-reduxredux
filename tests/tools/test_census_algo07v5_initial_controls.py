import copy
import json
import struct

import census_algo07v5_initial_controls as census
import numpy as np
import pytest

from leo.contracts.digests import canonical_digest


def initial():
    fit = dict(parameters=np.array([1., 2.]), score=3., evaluations=12,
               stopped='small_step_and_improvement',
               history=[dict(parameters=np.zeros(2), score=8.),
                        dict(parameters=np.array([1., 2.]), score=3.)])
    arms = {a: dict(phase_rounds=[dict(epoch=0, phase_reference=np.zeros(3),
                                     fit=copy.deepcopy(fit))]) for a in census.ARMS}
    return dict(selected_hypothesis=9,
                choices=[dict(hypothesis=2, arms={}), dict(hypothesis=9, arms=arms)],
                zero_phase_control={a: copy.deepcopy(fit) for a in census.ARMS})


def test_selected_hypothesis_lookup_and_complete_fit_comparison():
    evidence = initial()
    assert [r['status'] for r in census.compare_initial(evidence)] == ['matching', 'matching']
    evidence['zero_phase_control']['fitted_c']['evaluations'] += 1
    evidence['zero_phase_control']['fitted_c']['history'][1]['score'] += 1
    evidence['zero_phase_control']['fitted_c']['stopped'] = 'iteration_budget'
    rows = census.compare_initial(evidence)
    assert rows[0]['status'] == 'matching'
    assert rows[1]['status'] == 'mismatching'
    assert {m['path'] for m in rows[1]['mismatches']} == {
        "$['evaluations']", "$['history'][1]['score']", "$['stopped']"}
    assert rows[1]['first_fit_sha256'] != rows[1]['control_fit_sha256']


@pytest.mark.parametrize(('left', 'right'), [
    (1, True), (1., np.float64(1.)), (0., -0.), ([1], (1,)),
    (np.array([1], dtype='i4'), np.array([1], dtype='i8')),
    (np.array([1., 2.]), np.array([[1., 2.]])),
    (struct.unpack('>d', bytes.fromhex('7ff8000000000001'))[0],
     struct.unpack('>d', bytes.fromhex('7ff8000000000002'))[0]),
    (np.array([0.]), np.array([-0.])),
    ({'a': 1}, {'a': 1, 'b': 2}),
])
def test_exact_types_float_payloads_and_array_metadata(left, right):
    assert census.differences(left, right)
    assert census.fingerprint(left) != census.fingerprint(right)


def test_equal_nan_payload_and_mapping_order_are_exact():
    nan = struct.unpack('>d', bytes.fromhex('7ff8000000000001'))[0]
    left = dict(a=nan, b=np.array([nan]))
    right = dict(b=np.array([nan]), a=nan)
    assert census.differences(left, right) == []
    assert census.fingerprint(left) == census.fingerprint(right)


def test_missing_history_entries_have_explicit_paths():
    issues = census.differences([1, 2, 3], [1])
    assert [r['path'] for r in issues] == ['$', '$[1]', '$[2]']
    assert all(r['missing_in'] == 'right' for r in issues[1:])


def test_zero_context_and_missing_arms_are_not_matches():
    evidence = initial()
    evidence['choices'][1]['arms']['c0']['phase_rounds'][0]['phase_reference'][0] = 1
    evidence['zero_phase_control']['c0']['history'][0]['parameters'][0] = 1
    del evidence['zero_phase_control']['fitted_c']
    rows = census.compare_initial(evidence)
    assert rows[0]['context'] == dict(epoch_zero=True, zero_reference=False, zero_start=False)
    assert rows[0]['status'] == 'mismatching'
    assert rows[1]['status'] == 'missing'


@pytest.mark.parametrize('wrapped', [False, True])
def test_cli_loads_explicit_requests_and_preserves_public_bindings(tmp_path, monkeypatch, wrapped):
    identity = dict(run_id='run', session_id='session', input_sha256='sha256:input')
    job = dict(output_root=str(tmp_path), identity=identity)
    request = dict(job=job, algorithm='algo07v4-native-v1') if wrapped else job
    path = tmp_path / 'request.json'
    path.write_text(json.dumps(request))
    receipt = dict(result_sha256='sha256:archive', result_bytes=99, **identity)
    saved = dict(receipt=receipt, sha256='sha256:receipt',
                 evidence=dict(identity=identity, audit=dict(initial=initial()),
                               provenance=dict(request_sha256=canonical_digest(request),
                                               configuration=dict(request=job))))
    calls = []

    class Store:
        def __init__(self, root):
            assert root == tmp_path

        def load(self, run_id):
            calls.append(run_id)
            return saved

    monkeypatch.setattr(census, 'LocalizationV4Store' if wrapped else 'LocalizationV3Store', Store)
    assert census.main(['--request', str(path), '--output', str(tmp_path / 'result')]) == 0
    report = json.loads((tmp_path / 'result' / 'census.json').read_text())
    assert calls == ['run']
    assert report['counts'] == dict(matching=2, mismatching=0, missing=0)
    run = report['requests'][0]
    assert run['archive_sha256'] == receipt['result_sha256']
    assert run['archive_bytes'] == 99
    assert run['receipt_sha256'] == 'sha256:receipt'
    assert run['request_sha256'] == canonical_digest(request)
    saved['evidence']['provenance']['request_sha256'] = 'wrong'
    assert census.main(['--request', str(path), '--output', str(tmp_path / 'bad')]) == 1
    assert json.loads((tmp_path / 'bad' / 'census.json').read_text())['counts']['missing'] == 2


def test_pilot_ledger_selects_only_eight_baseline_requests(tmp_path, monkeypatch):
    ledger = tmp_path / 'ledger.json'
    rows = [dict(case=f'SCAN-{i}', config='baseline', output=str(tmp_path / str(i)))
            for i in range(8)]
    ledger.write_text(json.dumps(dict(runs=[*rows, dict(config='cheap64')])))
    seen = []

    def read(path):
        seen.append(path)
        return dict(arms=[dict(arm=a, status='matching') for a in census.ARMS])

    for i in range(8):
        folder = tmp_path / str(i)
        folder.mkdir()
        (folder / 'request.json').write_text('{}')
    monkeypatch.setattr(census, 'census_request', read)
    assert census.main(['--pilot-ledger', str(ledger), '--output', str(tmp_path / 'result')]) == 0
    assert seen == [tmp_path / str(i) / 'request.json' for i in range(8)]
    report = json.loads((tmp_path / 'result' / 'census.json').read_text())
    assert str(ledger) in report['input_bindings']
    assert report['counts']['matching'] == 16
