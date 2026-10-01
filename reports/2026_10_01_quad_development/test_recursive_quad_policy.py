import json
import sys
from pathlib import Path
import run_recursive_quad as runner


def setup(monkeypatch,tmp_path):
    binding=dict(unit_id='DS9-B01-Q',block_id='DS9-B01',size=4,scans=['DS9-F001','DS9-F002','DS9-F003','DS9-F004'])
    runner.save(tmp_path/'selection.json',dict(evaluation_units=[binding]))
    for name in ['RECURSIVE_QUAD_PLAN.md','test_recursive_quad_starts.py','test_recursive_quad_policy.py']:
        (tmp_path/name).write_text('test fixture')
    (tmp_path/'test_constituent_policy_failures.py').write_text('test source fixture')
    goal=tmp_path/'goal';goal.mkdir()
    monkeypatch.setattr(runner,'HERE',tmp_path);monkeypatch.setattr(runner,'GOAL',goal)
    monkeypatch.setattr(sys,'argv',['runner',binding['unit_id']])
    def forbidden(*args,**kwargs):raise AssertionError('must not fit')
    monkeypatch.setattr(runner,'execute',forbidden)
    return binding,tmp_path/'recursive-quad-v1'/binding['unit_id']


def test_missing_constituent_remains_an_explicit_failed_outcome(monkeypatch,tmp_path):
    binding,directory=setup(monkeypatch,tmp_path)
    def missing(unit):raise FileNotFoundError('missing constituent audit')
    monkeypatch.setattr(runner,'admit',missing)
    runner.main()
    row=json.loads((directory/'evaluation.json').read_text())['rows'][0]
    assert row['unit']==binding['unit_id'] and not row['accepted']
    assert row['error_m'] is None and row['runtime_s'] is None
    assert 'FileNotFoundError' in row['failures'][0]


def test_insufficient_budget_records_charged_constituent_work(monkeypatch,tmp_path):
    binding,directory=setup(monkeypatch,tmp_path)
    records=[({},dict(elapsed_seconds=180.)),({},dict(elapsed_seconds=175.))]
    monkeypatch.setattr(runner,'admit',lambda unit:(binding,records,{},{}))
    runner.main()
    row=json.loads((directory/'evaluation.json').read_text())['rows'][0]
    assert not row['accepted'] and row['runtime_s']==355.
    assert row['failures']==['insufficient_budget'] and row['error_m'] is None


def test_joint_launch_uses_only_remaining_budget_and_charges_both_stages(monkeypatch,tmp_path):
    binding,directory=setup(monkeypatch,tmp_path)
    records=[({},dict(elapsed_seconds=40.)),({},dict(elapsed_seconds=43.))]
    monkeypatch.setattr(runner,'admit',lambda unit:(binding,records,{},{}))
    def execute(command,where,name,timeout_s,env):
        assert timeout_s==277. and command[-2:]==['--seconds','277.0']
        assert env['OPENBLAS_NUM_THREADS']=='1'
        (where/(name+'.json')).write_text('{}')
        return dict(elapsed_seconds=7.,within_budget=True,returncode=0,timed_out=False)
    audited=[]
    monkeypatch.setattr(runner,'execute',execute)
    monkeypatch.setattr(runner,'evaluate',lambda directory:audited.append(directory))
    runner.main()
    launch=json.loads((directory/(binding['unit_id']+'.launch.json')).read_text())
    assert launch['constituent_cost_s']==83. and launch['joint_launch_seconds']==7.
    assert launch['elapsed_seconds']==90. and launch['within_budget']
    assert audited==[directory]
