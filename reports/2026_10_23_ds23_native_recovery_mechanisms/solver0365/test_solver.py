"""Owned mechanism checks on completed evidence and constrained optimizer."""
import numpy as np
import run_solver as s

def test_existing_feasible_solver_enforces_gate():
    result=s.feasible_fit(lambda x:float((x[0]-2)**2),lambda x:[1-x[0]],
        np.array([0.]),np.array([-3.]),np.array([3.]),iterations=40)
    assert result['feasible'] and result['parameters'][0]<=1
    assert .99<result['parameters'][0]

def test_frozen_replay_and_matched_budgets():
    data=s.read(s.OUT/'results.json')
    assert data['protocol']['rounds']==5 and data['protocol']['iterations_per_round']==40
    for case in data['cases']:
        for replay in case['replay'].values():
            assert all(abs(r['saved_objective_difference'])<1e-5 for r in replay.values())
        for arm in ['c0','fitted_c']:
            rows=[r for r in case['fits'] if r['arm']==arm]
            assert len(rows)==2
            assert rows[0]['start']==rows[1]['start']
            assert rows[0]['start_phase_reference']==rows[1]['start_phase_reference']
            for row in rows:
                assert len(row['history'])==5
                assert all(h['fit']['iterations']<=40 for h in row['history'])
                summary=row['summary']
                assert summary['qualified']==s.qualifies(summary)
                assert (row['interpretation']=='diagnostic_only')== (not summary['qualified'])
