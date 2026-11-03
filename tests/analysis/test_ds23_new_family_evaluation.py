from types import SimpleNamespace

import numpy as np
import pytest

import evaluate_ds23_new_family_prediction as evaluation


def test_joint_ownership_counts_unique_original_ids_and_omits_conflicting_postfit_row(monkeypatch):
    rows=[dict(component='old',compatible=True,norad=1,points=2),
          dict(component='extension',compatible=True,norad=2,points=2)]
    monkeypatch.setattr(evaluation.runner.engine.baseline,'build',lambda *args:None)
    monkeypatch.setattr(evaluation,'retained_metrics',lambda *args:None)
    monkeypatch.setattr(evaluation,'extend_associations',lambda *args:dict(tracks=rows))
    d=dict(scan=SimpleNamespace(tracks=[dict(key='old',observation_ids=['a','b']),
        dict(key='extension',observation_ids=['c','d'])]),observations=[dict(observation_id=o) for o in 'abcde'])
    new=[dict(component='new',observation_ids=['c','e'],norad=3,points=2)]
    result=evaluation.coverage(d,'c0',dict(phase_reference=[],endpoint_east_north_km=[0,0]),new)
    assert result['accepted_observation_ids']==['a','b','c','e']
    assert result['associated']==4 and result['associated_tracks']==2
    assert result['conflicting_postfit_only_extensions_omitted'][0]['component']=='extension'


def test_coverage_rejects_synthetic_measurement_ids(monkeypatch):
    monkeypatch.setattr(evaluation.runner.engine.baseline,'build',lambda *args:None)
    monkeypatch.setattr(evaluation,'retained_metrics',lambda *args:None)
    monkeypatch.setattr(evaluation,'extend_associations',lambda *args:dict(tracks=[]))
    d=dict(scan=SimpleNamespace(tracks=[]),observations=[dict(observation_id='real')])
    with pytest.raises(ValueError,match='synthetic'):
        evaluation.coverage(d,'c0',dict(phase_reference=[],endpoint_east_north_km=[0,0]),
            [dict(component='new',observation_ids=['synthetic'],norad=3,points=1)])


def test_full_summary_keeps_regressions_and_uses_original_glrt_weighted_coverage():
    rows=[]
    for arm in ['c0','fitted_c']:
        for method in ['incumbent','phase_only','physical_prior']:
            for case,error,total,associated in [('A',1.,10,5),('B',2.,100,50)]:
                delta=(1. if case=='A' else -.2) if method!='incumbent' else 0.
                rows.append(dict(case=case,arm=arm,method=method,position_error_km=error+delta,
                    accepted=method!='incumbent',total_GLRT=total,associated_points=associated,
                    new_prediction_points=0,original_accepted_points_lost=0,frequency_RMS_hz=100.))
    result=evaluation.summary(rows,bootstrap_count=30)
    r=next(r for r in result if r['arm']=='fitted_c' and r['method']=='physical_prior')
    assert r['cases']==2 and r['regressions_over500m']==1
    assert r['associated_percent']==pytest.approx(50.)
    assert r['mean_error_km']==pytest.approx(1.9)
    assert np.isfinite(r['mean_improvement_scan_bootstrap95_km']).all()
