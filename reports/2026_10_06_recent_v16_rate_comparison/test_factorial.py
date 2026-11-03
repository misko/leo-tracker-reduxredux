"""Factorial adapter tests; scientific gradient check explicitly corpus-marked."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
import factorial as study
from original_candidates import top_rows


def test_eight_cases_and_original_top_candidate_tie_break():
    assert len(set(study.cases()))==8
    assert len(study.stage.ARMS)*len(study.cases())==16
    records=[dict(group_id=g,original_margin=m,row_index=i) for g,m,i in
             [('a',.2,2),('a',.7,3),('b',.8,5),('b',.8,4)]]
    assert top_rows(records)==[3,4]


def test_branch_scheduling_does_not_change_scientific_cases():
    from run_factorial_bounded import planned_jobs
    both=planned_jobs('a')
    original=planned_jobs('a',['original'])
    refined=planned_jobs('a',['refined'])
    assert len(both)==9 and len(original)==5 and len(refined)==4
    assert both==original+refined
    assert original[0][0]=='original'
    assert all(name.startswith('refined-') for name,args in refined)
    with pytest.raises(ValueError):planned_jobs('a',[])


def test_error_differences_only_use_completed_matched_scans():
    from summarize_factorial import paired_changes
    base=dict(scan='a',refinement='original',model='T1AT',cone='off',arm='fitted-c',
              status='complete',distance_m=1000.,converged=True,boundary=False)
    rows=[base,dict(base,model='V16',distance_m=700.),
          dict(base,scan='b',model='V16',distance_m=100.),
          dict(base,refinement='refined',status='pending',distance_m=None)]
    pairs=paired_changes(rows)
    assert len(pairs)==1 and pairs[0]['change_m']==-300.
    assert pairs[0]['both_converged'] and not pairs[0]['either_boundary']


def test_original_loader_has_no_refinement_dependency(tmp_path,monkeypatch):
    import original_candidates as original
    import sys
    monkeypatch.setitem(sys.modules,'oracle_position_diagnostic',SimpleNamespace(reference_coordinates=lambda *args:(0.,0.)))
    records=[dict(row_index=i,group_id=i//2,time_s=i//2,original_hz=10.+i,original_margin=i+.1,
                  rf_hz=11e9,receiver=0,channel=1) for i in range(4)]
    obs=tmp_path/'observations.json';obs.write_text(json.dumps(dict(records=records,origin_utc_ns=0,summary={'session_id':'synthetic'})))
    bank=tmp_path/'orbit-bank';bank.mkdir()
    np.savez(bank/'states.npz',nodes_s=[-20,320],numbers=[1,2],position_km=np.zeros((2,2,3)),velocity_km_s=np.zeros((2,2,3)))
    (bank/'receipt.json').write_text(json.dumps(dict(signature={'observations_sha256':original.digest(obs.read_bytes())},
        arrays_sha256=original.digest((bank/'states.npz').read_bytes()))))
    data=original.load(tmp_path)
    np.testing.assert_array_equal(data.original_rows,[1,3])
    np.testing.assert_array_equal(data.measured,[11.,13.])
    assert not (tmp_path/'refinement').exists()


@pytest.mark.real_corpus
def test_frozen_cone_training_scans_are_earlier_and_disjoint():
    cone=json.loads((study.stage.ROOT/'reports/2026_10_05_receiver_cones/summary.json').read_text())
    earlier=json.loads((study.stage.ROOT/'reports/2026_10_05_receiver_sky_82/cohort.json').read_text())['scans']
    recent=json.loads(study.stage.COHORT.read_text())['scans']
    training=[r for r in earlier if r['label'] in cone['completed_scans']]
    assert len(training)==len(cone['completed_scans'])==20
    assert not {r['session_id'] for r in training}&{r['session_id'] for r in recent}
    assert max(r['capture_end_ns'] for r in training)<min(r['capture_start_ns'] for r in recent)


@pytest.mark.real_corpus
def test_cone_zero_strength_score_gradient_parity_and_nonzero_gradient():
    from factorial_objective import Objective
    from position_score_sweep import Objective as Base,SPECS
    from timing_bound_comparison import feasible_start
    folder=study.SOURCE/'positions/R025-01'
    with np.load(folder/'input.npz') as z: data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    for field in ('times','measured','rf','receiver','channel','group','margin','original_rows','owners','fixed_receiver_hz'):
        setattr(data,field,getattr(data,field)[::70])
    receipt=json.loads((folder/'fitted-c.json').read_text());center=receipt['input_metadata']['rf_center_hz']
    for spec in ('C0','V16'):
        base=Base(data,center,'fitted-c',SPECS[spec]);v=feasible_start(base,receipt['best'],20.,'fitted-c')
        value,gradient=base.evaluate(v)
        zero=Objective(data,center,'fitted-c',SPECS[spec],strength=0.)
        value0,g0=zero.evaluate(v)
        np.testing.assert_allclose(value0,value,rtol=0,atol=1e-8)
        np.testing.assert_allclose(g0,gradient,rtol=0,atol=1e-7)
        cone=Objective(data,center,'fitted-c',SPECS[spec]);_,g=cone.evaluate(v)
        for i in (0,1,2,3,6,7,len(v)-1):
            step=1e-3 if i in (2,len(v)-1) else 1e-5
            delta=np.eye(len(v))[i]*step
            numeric=(cone.evaluate(v+delta)[0]-cone.evaluate(v-delta)[0])/(2*step)
            np.testing.assert_allclose(g[i],numeric,rtol=5e-4,atol=5e-4)
