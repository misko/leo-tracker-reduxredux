"""Audit matched-support diagnostics without changing the failed phase gate."""
import json
from pathlib import Path
import subprocess
import sys
from verify import digest

HERE=Path(__file__).resolve().parent


def main():
    visited=set();bindings=0
    def check(path):
        nonlocal bindings
        path=Path(path)
        if path in visited:return
        visited.add(path)
        if path.suffix!='.json':return
        data=json.loads(path.read_text())
        if not isinstance(data,dict):return
        sources=data.get('sources',{})
        if not isinstance(sources,dict):return
        for name,expected in sources.items():
            if not Path(name).is_absolute():continue
            assert digest(name)==expected,(path,name)
            bindings+=1;check(name)
    paths=[HERE/n for n in ('fragment-diagnostic.json','fragment-coverage.json','summary.json')]
    for path in paths:check(path)
    test=subprocess.run([sys.executable,'-m','unittest','test_model','test_fragment'],
                        cwd=HERE,capture_output=True,text=True,timeout=60)
    assert test.returncode==0,test.stdout+test.stderr
    assert not json.loads((HERE/'summary.json').read_text())['passed']
    out=dict(passed=True,previous_goal_turn='progress: unanchored phase-gap feasibility rejected',
             verified_bindings=bindings,unique_dependencies=len(visited),component_tests_passed=5,
             test_output=test.stdout+test.stderr,original_feasibility_gate_passed=False,
             causal_position_improvement_established=False,goal_status='active',
             sources={str(p):digest(p) for p in paths+[Path(__file__),HERE/'verify.py',HERE/'test_fragment.py',HERE/'test_model.py']})
    with (HERE.parent/'progress-audit-18.json').open('x') as f:json.dump(out,f,indent=2)
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
