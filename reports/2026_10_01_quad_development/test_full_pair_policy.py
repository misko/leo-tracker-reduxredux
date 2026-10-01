import json
import sys
from pathlib import Path
import run_constituent_pair_v3 as runner


def setup(monkeypatch,tmp_path):
    binding=dict(unit_id='DS9-B06-D2',block_id='DS9-B06',size=2,scans=['DS9-F099','DS9-F100'])
    runner.save(tmp_path/'selection.json',dict(evaluation_units=[binding]))
    (tmp_path/'CONSTITUENT_START_PLAN.md').write_text('test plan')
    (tmp_path/'FULL_PAIR_PLAN.md').write_text('full panel plan')
    (tmp_path/'test_constituent_policy_failures.py').write_text('test source fixture')
    goal=tmp_path/'goal';goal.mkdir()
    monkeypatch.setattr(runner,'HERE',tmp_path);monkeypatch.setattr(runner,'GOAL',goal)
    monkeypatch.setattr(sys,'argv',['runner',binding['unit_id']])
    def forbidden(*args,**kwargs):raise AssertionError('must not fit')
    monkeypatch.setattr(runner,'execute',forbidden)
    return binding,tmp_path/'constituent-pair-v3'/binding['unit_id']


def test_missing_constituent_remains_an_explicit_failed_outcome(monkeypatch,tmp_path):
    binding,directory=setup(monkeypatch,tmp_path)
    def missing(unit):raise FileNotFoundError('missing constituent audit')
    monkeypatch.setattr(runner,'constituents',missing)
    runner.main()
    row=json.loads((directory/'evaluation.json').read_text())['rows'][0]
    assert row['unit']==binding['unit_id'] and not row['accepted']
    assert row['error_m'] is None and row['runtime_s'] is None
    assert 'FileNotFoundError' in row['failures'][0]


def test_insufficient_budget_records_charged_constituent_work(monkeypatch,tmp_path):
    binding,directory=setup(monkeypatch,tmp_path)
    records=[({},dict(elapsed_seconds=90.)),({},dict(elapsed_seconds=85.))]
    monkeypatch.setattr(runner,'constituents',lambda unit:(binding,records,{},{}))
    runner.main()
    row=json.loads((directory/'evaluation.json').read_text())['rows'][0]
    assert not row['accepted'] and row['runtime_s']==175.
    assert row['failures']==['insufficient_budget'] and row['error_m'] is None


def test_joint_launch_uses_only_remaining_budget_and_charges_both_stages(monkeypatch,tmp_path):
    binding,directory=setup(monkeypatch,tmp_path)
    records=[({},dict(elapsed_seconds=40.)),({},dict(elapsed_seconds=43.))]
    monkeypatch.setattr(runner,'constituents',lambda unit:(binding,records,{},{}))
    def execute(command,where,name,timeout_s,env):
        assert timeout_s==97. and command[-2:]==['--seconds','97.0']
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
