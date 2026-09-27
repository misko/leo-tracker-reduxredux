"""Offline provenance, track membership, split and numerical checks."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    return json.loads((HERE / name).read_text())


def test_exact_membership_and_frozen_visit_partitions():
    plan = load('plan.json')
    path = HERE.parent / '2026_09_27_ds6_alltrack_phase/inputs.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == plan['source_inputs_sha256']
    inputs = json.loads(path.read_text())
    assert inputs['input_manifest_sha256'] == plan['input_manifest_sha256']
    tracks = {t['track_id']: t for t in inputs['tracks']}
    assignments = {}
    for v in plan['selected']:
        assert len({m['rx0_track_id'] for m in v['modes']}) == 2
        for rx in [0, 1]:
            assert len({m['candidate_ids'][rx] for m in v['modes']}) == 2
        for m in v['modes']:
            t = tracks[m['rx0_track_id']]
            assert t['receiver_id'] == 0
            k = t['candidate_ids'].index(m['candidate_ids'][0])
            assert t['visits'][k] == v['visit']
            assert t['training_mask'][k] == (v['partition'] == 'train')
        assert assignments.setdefault(v['visit'],v['partition']) == v['partition']


def test_replay_accounting_and_bindings():
    plan, replay = load('plan.json'), load('replay.json')
    assert replay['complete']
    assert replay['plan_sha256'] == hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest()
    expected = {(v['visit'],v['group'],ms) for v in plan['selected'] for ms in plan['starts_ms']}
    actual = [(r['visit'],r['group'],r['start_ms']) for r in replay['rows']]
    assert len(actual) == len(set(actual)) and set(actual) == expected
    visits = {(v['visit'],v['group']) for v in plan['selected']}
    for key in ['controls', 'audits']:
        assert len(replay[key]) == len(visits)
        assert {(r['visit'],r['group']) for r in replay[key]} == visits


def test_response_uses_disjoint_tracks_and_frozen_partitions():
    plan, protocol = load('plan.json'), load('response-protocol.json')
    selected = {(v['visit'],v['group']):v for v in plan['selected']}
    ids = []
    for group in protocol['observations']:
        ids.extend(group['track_ids'])
        for observation in group['observations']:
            v = selected[observation['visit'],group['group']]
            assert observation['train'] == (v['partition'] == 'train')
            assert group['track_ids'] == [m['rx0_track_id'] for m in v['modes']]
            assert observation['qualified_windows'] > 0
    assert len(ids) == len(set(ids))


def test_delay_quadrature_converges():
    result = load('response-results.json')
    for arm in ['independent_offsets','shared_delay','cfo_only']:
        for field in ['training_log_evidence','held_cfo_log_predictive']:
            assert abs(result['201']['scores'][arm][field]-result['401']['scores'][arm][field]) < 1e-4
    assert abs(result['201']['scores']['shared_delay']['held_phase_log_predictive']-
               result['401']['scores']['shared_delay']['held_phase_log_predictive']) < 1e-4


def test_common_rate_compares_exact_same_qualified_windows():
    replay, common = load('replay.json'), load('common-rate-results.json')
    assert common['replay_sha256']==hashlib.sha256((HERE/'replay.json').read_bytes()).hexdigest()
    assert common['plan_sha256']==hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest()
    expected={(r['visit'],r['group'],r['start_ms']) for r in replay['rows'] if r['original']['both_qualified']}
    actual=[(r['visit'],r['group'],r['start_ms']) for r in common['rows']]
    assert len(actual)==len(set(actual)) and set(actual)==expected
    for row in common['rows']:
        assert len(row['shared']['held_frame_errors_rad'])==len(row['independent']['held_frame_errors_rad'])
        assert len(set(row['shared']['rates_hz'].values()))==1
