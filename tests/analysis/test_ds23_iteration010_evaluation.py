from types import SimpleNamespace
import numpy as np
from evaluate_ds23_iteration010_short_confirmation import summarize,reported_fit


def test_summary_keeps_unchanged_scans_and_separates_accuracy_from_point_counts():
    rows=[]
    for arm in ['c0','fitted_c']:
        for method in ['Incumbent','Short whole-curve policy']:
            for case,error,n in [('a',1.,80),('b',3. if method=='Incumbent' else 4.,80 if method=='Incumbent' else 90)]:
                rows.append(dict(arm=arm,method=method,case=case,position_error_km=error,all_GLRT=100,associated_points=n,
                    RMS_hz=20. if method=='Incumbent' else 10.,selected_recovery=method!='Incumbent' and case=='b',
                    added_curved_points=10 if method!='Incumbent' and case=='b' else 0))
    summary=summarize(rows);old,new=[r for r in summary if r['arm']=='fitted_c']
    assert old['mean_error_km']==2. and new['mean_error_km']==2.5
    assert old['associated_percent']==80 and new['associated_percent']==85
    assert new['regressions_over500m']==1 and new['unchanged_cases']==1 and new['cases']==2
    assert old['new_curved_points']==0 and old['selected_cases']==0


def test_missing_refresh_field_is_measured_at_saved_endpoint_without_refitting():
    problem=SimpleNamespace(labels=[1],state=lambda x:dict(phases=np.array([0.,2.2])))
    saved=dict(endpoint_east_north_km=[1.,2.],phase_reference=[2.199])
    result=reported_fit(problem,saved)
    assert abs(result['final_phase_change_s']-.001)<1e-12
    assert 'final_phase_change_s' not in saved
