"""Audit pilot coverage, training selection, provenance and qualification."""
import json
from pathlib import Path
import subprocess
import sys
from common import HERE,JOBS,read,digest
from gate import assess


def main():
    visited=set();bindings=0
    def check(path):
        nonlocal bindings
        path=Path(path)
        if path in visited:return
        visited.add(path)
        if path.suffix!='.json':return
        doc=read(path)
        if not isinstance(doc,dict):return
        sources=doc.get('sources',{})
        if not isinstance(sources,dict):return
        for p,h in sources.items():
            if not Path(p).is_absolute():continue
            assert digest(p)==h,(path,p)
            bindings+=1;check(p)
    sp=HERE/'summary.json';summary=read(sp);check(sp);sealed=read(HERE/'sealed.json')
    assert len(sealed['cells'])==12 and len(summary['rows'])==6
    assert summary['families']==assess(summary['rows'])
    count=qualified=selected_count=0;times=[]
    for c in sealed['cells']:
        valid=[]
        assert len(c['attempts'])==2
        for a in c['attempts']:
            count+=1;receipt=a['receipt'];times.append(receipt['elapsed_s'])
            if a['result'] and a['result']['qualified']:valid.append(a['result']);qualified+=1
        expected=max(valid,key=lambda r:r['score']) if valid else None
        assert c['selected']==expected;selected_count+=expected is not None
    assert count==24
    original_failure=next(r for r in summary['rows'] if r['cohort']=='additional' and r['index']==9)
    assert original_failure['original_iid']==dict(qualified=False,error_m=None)
    for cohort,index,_ in JOBS:
        preflight=HERE/f'preflight-{cohort}-{index:02d}.json';check(preflight)
        assert read(preflight)['passed']
    test=subprocess.run([sys.executable,'-m','unittest','test_load','test_gate'],cwd=HERE,capture_output=True,text=True,timeout=60)
    assert test.returncode==0,test.stdout+test.stderr
    result=dict(passed=True,previous_goal_turn='progress: frozen family0/1 receiver transfer passed',
                verified_bindings=bindings,unique_dependencies=len(visited),component_tests_passed=4,
                test_output=test.stdout+test.stderr,attempted_position_starts=count,qualified_position_starts=qualified,
                qualified_cells=selected_count,maximum_fit_worker_s=max(times),families=summary['families'],
                original_baseline_failure_retained=True,causal_position_improvement_established=False,goal_status='active',
                sources={str(p):digest(p) for p in (Path(__file__),sp,HERE/'test_load.py',HERE/'test_gate.py')})
    with (HERE.parent/'progress-audit-25.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
