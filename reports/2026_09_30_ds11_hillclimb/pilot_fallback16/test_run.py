import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("waveform_position_replication_test", Path(__file__).with_name("run.py"))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def example():
    track = dict(track_id="target", y=np.array([100., 200., 300.]),
                 mask=np.array([True, False, True]), times_s=np.array([1., 2., 3.]),
                 visits=[10, 20, 30], candidate_position_km=np.zeros((2, 3, 3)))
    correction = dict(track_id="target", observation_index=0, visit=10,
                      time_s=1., measured_hz=100., delta_hz=5.)
    return [dict(tracks=[track])], correction


def test_only_requested_training_value_changes_and_original_stays_intact():
    documents, correction = example()
    result = run.patch_documents(documents, [correction])
    np.testing.assert_array_equal(result[0]["tracks"][0]["y"], [105., 200., 300.])
    np.testing.assert_array_equal(documents[0]["tracks"][0]["y"], [100., 200., 300.])
    assert result[0]["tracks"][0]["candidate_position_km"] is documents[0]["tracks"][0]["candidate_position_km"]


@pytest.mark.parametrize("change", [dict(observation_index=1), dict(track_id="absent"),
                                    dict(measured_hz=101.), dict(time_s=1.1), dict(visit=11)])
def test_held_missing_or_mismatched_correction_is_rejected(change):
    documents, correction = example()
    with pytest.raises(AssertionError):
        run.patch_documents(documents, [dict(correction, **change)])


def test_duplicate_correction_is_rejected():
    documents, correction = example()
    with pytest.raises(AssertionError):
        run.patch_documents(documents, [correction, correction])


def test_nominal_center_matches_analytic_center_and_shifts_only_training():
    epoch = 4458.014573888774
    for arm, mean_symbol in zip(run.ARMS, (33.5, 121.5)):
        analytic = epoch/5e6 + 3.5/750 + (mean_symbol*1056+527.5)/240e6
        assert abs(run.nominal_center(epoch, arm)-analytic) < 3e-9
    documents, correction = example()
    result = run.patch_documents(documents, [dict(correction, nominal_support_shift_s=-.0042)])
    np.testing.assert_array_equal(result[0]['tracks'][0]['nominal_support_shift_s'], [-.0042, 0., 0.])
    assert 'nominal_support_shift_s' not in documents[0]['tracks'][0]



@pytest.mark.parametrize('disagreement,boundary,expected', [(99.,False,True),(100.,False,True),(100.01,False,False),(0.,True,False)])
def test_fallback_rule(disagreement,boundary,expected):
    full = dict(native_residual_hz=10., search_boundary=boundary)
    diagnostic = dict(alternating_native_hz=[0., disagreement], alternating_search_boundaries=[False,False])
    assert run.fallback_decision(full, diagnostic, 11.2e9)[0] == expected
    if disagreement == 100.01:
        assert run.fallback_decision(full, diagnostic, 22.4e9)[0]


def test_fallback_preserves_original_value_and_time():
    documents, correction = example()
    changed = run.patch_documents(documents, [dict(correction, delta_hz=0., nominal_support_shift_s=0., pilot_used=False)])
    np.testing.assert_array_equal(changed[0]['tracks'][0]['y'], documents[0]['tracks'][0]['y'])
    assert not np.any(changed[0]['tracks'][0]['nominal_support_shift_s'])


def test_selections_precede_both_scan_geography(tmp_path, monkeypatch):
    monkeypatch.setattr(run, 'HERE', tmp_path)
    other = tmp_path/'other'; other.mkdir()
    monkeypatch.setattr(run, 'OTHER', other)
    (tmp_path/'run.py').write_text('# test source')
    def distance(point):
        assert (tmp_path/'selections.json').exists() and (other/'selections.json').exists()
        return point[0]
    monkeypatch.setattr(run, 'context', lambda plan:([], None, None, SimpleNamespace(distance=distance)))
    monkeypatch.setattr(run, 'held_score', lambda *args:0.)
    jobs = [dict(arm=arm, seed_index=i, seed=[0.,0.,0.]) for arm in run.ARMS for i in range(4)]
    plan = dict(scan_index=16, jobs=jobs, config={}, control=dict(x=[0.,0.,0.], estimate_deg=[1.,0.]))
    run.write(tmp_path/'plan.json', plan)
    (tmp_path/'runs').mkdir()
    for i, job in enumerate(jobs):
        run.write(tmp_path/'runs'/f'{i:02d}.receipt.json', dict(job_index=i, exit_code=0, plan_sha256=run.digest(tmp_path/'plan.json')))
        run.write(tmp_path/'runs'/f'{i:02d}.json', dict(job_index=i, job=job, plan_sha256=run.digest(tmp_path/'plan.json'),
            endpoint=dict(qualified=True, score=float(job['seed_index']), x=[0.,0.,0.], estimate_deg=[10.+i,0.])))
    monkeypatch.setattr(run.sys, 'argv', ['run.py','seal'])
    run.assess()
    assert not (tmp_path/'outcome.json').exists()
    monkeypatch.setattr(run.sys, 'argv', ['run.py','assess'])
    with pytest.raises(FileNotFoundError):
        run.assess()
    run.write(other/'plan.json', {})
    run.write(other/'selections.json', dict(complete=True, plan_sha256=run.digest(other/'plan.json')))
    run.assess()
    outcome = run.read(tmp_path/'outcome.json')
    assert outcome['selected'][run.ARMS[0]]['error_m'] == 13.
    assert outcome['selected'][run.ARMS[1]]['error_m'] == 17.
