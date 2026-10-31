import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.optimize as optimize

from algo04_numerical_helper import bounded_position_call,centered_minimize,patched_stages
from algo04_numerical_stage import run_stage


def problem():
    return SimpleNamespace(sky={'time_s':np.array([-20.,40.])},flat_times=np.array([0.,1.]),
        flat_labels=np.array([0,0]),labels=[0],reference=np.array([-15.]),linear_entries=[])


def test_selector_excludes_other_optimizers_dimensions_boxes_and_analytic_derivatives():
    box=[(-12.5,12.5)]*2
    assert bounded_position_call('L-BFGS-B',[0,0],box)
    assert not bounded_position_call('Powell',[0,0],box)
    assert not bounded_position_call('L-BFGS-B',[0],[(-12.5,12.5)])
    assert not bounded_position_call('L-BFGS-B',[0,0],[(-1,1)]*2)
    assert not bounded_position_call('L-BFGS-B',[0,0],box,jac=lambda x:x)


def test_explicit_annotation_limit15_is_overridden_and_aliases_restore(monkeypatch):
    import phase_reference_checks as phase
    import ds23_frequency_events as events
    p=problem();factory=lambda *a,**k:p
    monkeypatch.setattr(events,'make_event_problem',factory)
    original_phase=phase.phase_refresh;original_minimize=optimize.minimize
    with patched_stages(reference_limit_s=30,centered_lbfgsb=False) as state:
        assert optimize.minimize is original_minimize
        events.make_event_problem()
        updated,check=phase.phase_refresh(np.array([-15.2]),p.reference,limit_s=15.)
        np.testing.assert_allclose(updated,[-15.2])
        assert check['next_reference_domain']['curved']['in_domain']
        assert check['numerical_reference_limit_s']==30
        assert state['reference_updates'][0]['caller_limit_s']==15
    assert events.make_event_problem is factory
    assert phase.phase_refresh is original_phase


def test_predictive_bank_guard_rejects_update_and_restores_on_error(monkeypatch):
    import ds23_frequency_events as events
    import ds23_predictive_linear as linear
    import phase_reference_checks as phase
    p=problem();p.reference=np.zeros(1);p.linear_entries=[{}]
    monkeypatch.setattr(events,'make_event_problem',lambda *a,**k:p)
    monkeypatch.setattr(linear,'linear_geometry',lambda *a: (SimpleNamespace(flat_times=np.array([-10.]),flat_labels=np.array([0])),))
    original=phase.phase_refresh
    with pytest.raises(ValueError,match='no extrapolation'):
        with patched_stages(reference_limit_s=30):
            events.make_event_problem()
            phase.phase_refresh(np.array([-15.2]),p.reference)
    assert phase.phase_refresh is original


def test_no_unchecked_refresh_without_captured_problem():
    import phase_reference_checks as phase
    with patched_stages(reference_limit_s=30):
        with pytest.raises(ValueError,match='no captured event problem'):
            phase.phase_refresh(np.zeros(1),np.zeros(1))


def test_centered_result_preserves_scipy_fields_and_counts_derivative_calls():
    calls=[]
    def objective(x,a,b):
        calls.append(np.array(x))
        return float((x[0]-a)**2+2*(x[1]-b)**2)
    original=optimize.minimize
    with patched_stages(reference_limit_s=30,centered_lbfgsb=True) as state:
        result=optimize.minimize(objective,np.array([1.,-2.]),args=(.5,-.25),method='L-BFGS-B',
            bounds=[(-12.5,12.5)]*2,options=dict(maxfun=240,maxiter=48,eps=.001,gtol=1e-4,maxls=20))
    assert optimize.minimize is original
    assert isinstance(result,optimize.OptimizeResult)
    assert result.success
    np.testing.assert_allclose(result.x,[.5,-.25],atol=1e-4)
    for key in ('x','fun','success','message','status','nit','nfev','njev','jac','hess_inv'):
        assert key in result
    np.testing.assert_array_equal(calls[0],[1.,-2.])
    assert result.nfev==len(calls)<=240
    assert result.numerical_maxls==40
    assert state['optimizer_calls'][0]['cap']==240
    assert state['extra_optimizer_rounds']==0


def test_hard_budget_cannot_report_success_or_hide_derivative_evaluations():
    calls=[]
    def objective(x):calls.append(1);return float(x@x)
    result=centered_minimize(optimize.minimize,objective,np.array([1.,-2.]),
        bounds=[(-12.5,12.5)]*2,options=dict(maxfun=2,maxiter=48))
    assert not result.success
    assert result.nfev==len(calls)==2
    assert result.status!=0
    assert np.isfinite(np.r_[result.x,result.fun,result.jac]).all()
    assert not result.jac_available


def test_boundary_derivatives_never_evaluate_outside_original_box():
    points=[]
    def objective(x):
        points.append(np.array(x));assert np.all(abs(x)<=12.5)
        return float(-x.sum())
    result=centered_minimize(optimize.minimize,objective,np.array([12.5,-12.5]),
        bounds=[(-12.5,12.5)]*2,options=dict(maxfun=240,maxiter=48,gtol=1e-4))
    assert result.success
    np.testing.assert_allclose(result.x,[12.5,12.5])
    assert result.nfev==len(points)<=240


def test_runpy_bootstrap_captures_policy_and_restores_state(tmp_path,monkeypatch):
    import ds23_frequency_events as events
    monkeypatch.setattr(events,'make_event_problem',lambda *a,**k:problem())
    script=tmp_path/'frozen_stage.py';receipt=tmp_path/'numerics.json'
    script.write_text('from ds23_frequency_events import make_event_problem\n'
        'from phase_reference_checks import phase_refresh\n'
        'import numpy as np\n'
        'p=make_event_problem()\n'
        'value,check=phase_refresh(np.array([-15.2]),p.reference,limit_s=15.)\n'
        'assert value[0]==-15.2\n')
    run_stage(script,[],reference_limit_s=30,centered_lbfgsb=True,receipt=receipt)
    record=json.loads(receipt.read_text())
    assert record['problem_count']==1
    assert record['reference_updates'][0]['numerical_reference_limit_s']==30
    assert record['restored_aliases']>0
    assert record['script_sha256']


def test_bootstrap_failure_still_records_and_restores(tmp_path):
    import phase_reference_checks as phase
    original=phase.phase_refresh;script=tmp_path/'failed.py';receipt=tmp_path/'receipt.json'
    script.write_text("raise RuntimeError('bounded failure')\n")
    with pytest.raises(RuntimeError,match='bounded failure'):
        run_stage(script,[],reference_limit_s=30,centered_lbfgsb=False,receipt=receipt)
    assert phase.phase_refresh is original
    assert json.loads(receipt.read_text())['stage_exception']['type']=='RuntimeError'


def test_runpy_main_from_import_gets_counted_centered_optimizer(tmp_path):
    script=tmp_path/'main_optimizer.py';receipt=tmp_path/'numerics.json'
    script.write_text('from scipy.optimize import minimize as position_minimize\n'
        'import numpy as np\n'
        'r=position_minimize(lambda x:float((x[0]-.5)**2+2*(x[1]+.25)**2),[1.,-2.],\n'
        'method="L-BFGS-B",bounds=[(-12.5,12.5)]*2,options={"maxfun":240,"maxiter":48})\n'
        'assert r.success and r.numerical_maxls==40\n'
        'assert r.nfev==r.total_physical_objective_evaluations<=240\n'
        'assert np.max(abs(r.x-np.array([.5,-.25])))<.0001\n')
    run_stage(script,[],reference_limit_s=30,centered_lbfgsb=True,receipt=receipt)
    record=json.loads(receipt.read_text())
    assert len(record['optimizer_calls'])==1
    assert record['optimizer_calls'][0]['start']==[1.,-2.]


def test_wrong_reference_owner_and_out_of_bank_final_posterior_are_rejected(monkeypatch):
    import ds23_frequency_events as events
    import phase_reference_checks as phase
    p=problem();monkeypatch.setattr(events,'make_event_problem',lambda *a,**k:p)
    with patched_stages(reference_limit_s=15):
        events.make_event_problem()
        with pytest.raises(ValueError,match='reference owner'):
            phase.phase_refresh(np.array([-15.2]),np.array([0.]))
        # The clipped next reference is in the bank; its unclipped physical
        # posterior is not. The guard must not hide that behind clipping.
        with pytest.raises(ValueError,match='no extrapolation'):
            phase.phase_refresh(np.array([-20.]),p.reference)

import copy
import json
from types import SimpleNamespace
import numpy as np
import pytest
import algo04_annotation_replay as replay


def test_overflow_trigger_checks_early_history_even_if_final_round_passes():
    a={'folds':[{'proposals':[{'arms':{'c0':{'phase_reference_check':{'phase_outside_reference_window':False},
        'history':[{'phase_outside_reference_window':True},{'phase_outside_reference_window':False}]}}}]}]}
    assert replay.has_phase_overflow(a)


def test_overflow_trigger_accepts_numeric_receipt_but_not_unrelated_convergence():
    assert replay.has_phase_overflow({'history':[{'maximum_phase_overflow_s':.001}]})
    assert not replay.has_phase_overflow({'final_phase_change_s':20,'history':[{'maximum_phase_overflow_s':0}]})


def test_frozen_signature_detects_alias_changes_and_does_not_mutate_source():
    source={'folds':[{'seed':1,'split':{'held_blocks':[2]},'proposals':[{'candidate_index':4,'norad':55,'alias':-1}]}]}
    before=copy.deepcopy(source);signature=replay.competition_signature(source)
    assert source==before
    source['folds'][0]['proposals'][0]['alias']=0
    assert replay.competition_signature(source)!=signature


def test_inactive_fragment_uses_validated_source_route(monkeypatch):
    import inactive_graph_fragment
    expected={'track_id':'parent','track_index':1,'component':'fragment','observation_ids':['a','b'],'inactive_graph_fragment':True}
    changed={'scan':SimpleNamespace(tracks=[None,{'key':'fragment','observation_ids':['a','b']}])}
    seen=[]
    def validated(d,inv,source):seen.append(source);return changed,copy.deepcopy(expected)
    monkeypatch.setattr(inactive_graph_fragment,'validated_inactive_context',validated)
    actual,target=replay.target_context({}, {}, {'track_id':'parent','component':'fragment','inactive_graph_fragment':True},
        {'target':expected},'frozen-source')
    assert actual is changed and target==expected and seen==['frozen-source']


def test_target_route_rejects_changed_fragment_observations(monkeypatch):
    import inactive_graph_fragment
    target={'track_id':'parent','track_index':0,'component':'fragment','observation_ids':['changed']}
    monkeypatch.setattr(inactive_graph_fragment,'validated_inactive_context',lambda *a:({'scan':SimpleNamespace(tracks=[{'key':'fragment','observation_ids':['changed']}])},target))
    with pytest.raises(ValueError,match='observation_ids changed'):
        replay.target_context({}, {}, {'track_id':'parent','component':'fragment','inactive_graph_fragment':True},
            {'target':dict(target,observation_ids=['original'])},'source')


def test_final_bank_check_rejects_extrapolated_actual_phase():
    p=SimpleNamespace(labels=[0],sky={'time_s':np.array([-2.,12.])},flat_times=np.array([10.]),flat_labels=np.array([0]),
        state=lambda x:{'phases':np.array([3.])})
    with pytest.raises(ValueError,match='causal orbit bank'):replay.check_bank(p,np.zeros(2))


def test_original_inventory_ids_may_be_sorted_while_native_graph_is_chronological():
    target={'track_id':'t','track_index':0,'component':'curve','observation_ids':['a','b'],'all_track_observation_ids':['b','a']}
    d={'scan':SimpleNamespace(tracks=[{'key':'curve','observation_ids':['b','a']}])}
    actual,_=replay.target_context(d,{'tracks':[target]},{'track_id':'t','component':'curve'}, {'target':target},'source')
    assert actual is d


def test_bootstrap_runs_under_production_read_guard_with_explicit_receipt(tmp_path):
    import os
    import subprocess
    import sys
    import algo04_numerical_stage as bootstrap

    repository = Path(bootstrap.__file__).resolve().parents[1]
    run = tmp_path / 'run'
    run.mkdir()
    script = run / 'position_stage.py'
    receipt = run / 'numerical.json'
    script.write_text(
        'from scipy.optimize import minimize\n'
        'r=minimize(lambda x:float(x@x),[1.,-2.],method="L-BFGS-B",'
        'bounds=[(-12.5,12.5)]*2,options={"maxiter":48,"maxfun":240})\n'
        'assert r.success and r.numerical_maxls==40\n'
    )
    environment = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE='1',
        PYTHONPATH=str(repository / 'deploy/fast_graph_guard'),
        LEO_FAST_GRAPH_RUN_ROOT=str(run),
        LEO_FAST_GRAPH_SOURCE_ROOT=str(repository),
        LEO_FAST_GRAPH_INPUT=str(run / 'tracking.json'),
        LEO_FAST_GRAPH_TLE_ROOT=str(run / 'archive'),
        MPLCONFIGDIR=str(run / 'matplotlib-cache'),
        OPENBLAS_NUM_THREADS='1',
        OMP_NUM_THREADS='1',
    )
    completed = subprocess.run(
        [sys.executable, '-B', bootstrap.__file__, '--reference-limit-s', '30',
         '--centered-lbfgsb', '--receipt', str(receipt), str(script)],
        env=environment, cwd=run, capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    numerical = json.loads(receipt.read_text())
    assert len(numerical['optimizer_calls']) == 1
    assert numerical['optimizer_calls'][0]['start'] == [1., -2.]
    reads = [json.loads(p.read_text()) for p in (run / 'read_receipts').glob('*.json')]
    assert len(reads) == 1
    assert reads[0]['denied_paths'] == []
    assert reads[0]['python_spawns'] == []
    assert str(script) in reads[0]['read_paths']


def test_annotation_replay_preserves_ids_aliases_and_saved_partitions(tmp_path, monkeypatch):
    import investigate_dsx01_localization_failures as fitter

    source = tmp_path / 'source'
    source.mkdir()
    ids = [f'point-{i}' for i in range(36)]
    target = dict(track_id='target', track_index=0, component='curve',
                  observation_ids=ids, all_track_observation_ids=ids)
    inventory = dict(job={'job_id': 'job'}, tracks=[target])
    seeds = [11, 12, 13]
    folds = [dict(seed=seed, split=dict(seed=seed, block_s=12., guard_s=0., held_blocks=[i]),
                  proposals=[dict(candidate_index=0, norad=55, alias=-1,
                                  arms={arm: dict(scores={'conditional_target': {
                                      'negative_twice_log_density': 10.}}) for arm in replay.ARMS})])
             for i, seed in enumerate(seeds)]
    frozen = dict(track_id='target', component='curve', folds=folds,
                  history=[{'maximum_phase_overflow_s': .2}])
    protocol = dict(job={'job_id': 'job'}, target=target, phase_step_s=.1,
                    uncalibrated_phase_mixture=False,
                    partition_plan={'schedule': dict(ready=True, selected=[
                        dict(seed=seed, target_held_blocks=[i]) for i, seed in enumerate(seeds)])})
    inventory_path = tmp_path / 'inventory.json'
    inventory_path.write_text(json.dumps(inventory))
    (source / 'result.json').write_text(json.dumps(frozen))
    (source / 'protocol.json').write_text(json.dumps(protocol))
    original_bytes = {p: p.read_bytes() for p in source.iterdir()}
    track = dict(key='curve', observation_ids=ids, times=np.arange(36.), values=np.arange(36.))
    base = SimpleNamespace(flat_times=np.array([-5., 40.]))
    context = dict(scan=SimpleNamespace(tracks=[track], norads=np.array([55])),
                   problems={'c0': (base, None)}, keep=np.ones(2, bool), node={})
    monkeypatch.setattr(replay, 'context', lambda _: context)
    monkeypatch.setattr(replay, 'check_predictive_role', lambda *a: None)
    monkeypatch.setattr(fitter, 'fit', lambda *a, **k: {'success': True, 'nfev': 5})
    seen_fits = []

    def fit_training(d, node, keep, arm, *, reference_limit_s):
        seen_fits.append((arm, keep.copy(), reference_limit_s))
        fitter.fit(None)
        p = SimpleNamespace(keep=keep.copy(), labels=[0], sky={'time_s': np.array([-40., 100.])},
                            flat_times=base.flat_times, flat_labels=np.zeros(2, int),
                            state=lambda x: {'phases': np.zeros(1)})
        return p, np.zeros(2), dict(history=[{}], final_phase_change_s=0.)

    monkeypatch.setattr(replay, 'fit_training', fit_training)
    monkeypatch.setattr(replay, 'prediction_models', lambda *a, **k: (
        np.zeros((1, 36)), np.eye(36)[None], np.zeros(1), np.zeros(1),
        np.full((1, 36), 10.), {'unchanged': True}))
    seen_scores = []

    def score(observed, mu, cov, lp, train, held):
        seen_scores.append((observed.copy(), train.copy(), held.copy()))
        return dict(negative_twice_log_density=9., rms_hz=1., training_mixture_weights=np.ones(1))

    monkeypatch.setattr(replay, 'mixture_prediction', score)
    monkeypatch.setattr(replay, 'identity_consensus', lambda *a, **k: {
        'status': 'conditionally_supported_identity', 'norad': 55})
    result = replay.replay_annotation(inventory_path, source, tmp_path / 'output')
    saved = json.loads((tmp_path / 'output/protocol.json').read_text())
    assert saved['target']['observation_ids'] == ids
    assert saved['partition_plan'] == protocol['partition_plan']
    assert replay.competition_signature(result) == replay.competition_signature(frozen)
    assert len(seen_fits) == len(seen_scores) == 6
    assert all(limit == 30. for _, _, limit in seen_fits)
    for i, fold in enumerate(folds):
        train, held = replay.replay_split(track['times'], fold['split'])
        for arm_index in range(2):
            observed, actual_train, actual_held = seen_scores[2*i+arm_index]
            np.testing.assert_array_equal(observed, track['values'] - replay.PERIOD)
            np.testing.assert_array_equal(actual_train, train)
            np.testing.assert_array_equal(actual_held, held)
    assert all(p.read_bytes() == body for p, body in original_bytes.items())
