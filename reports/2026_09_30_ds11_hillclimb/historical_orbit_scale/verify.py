"""Verify historical uncertainty evidence and report unavailable confirmation."""
import json
from pathlib import Path
import subprocess
import sys
from run import digest

HERE=Path(__file__).resolve().parent


def main():
    paths=[HERE/n for n in ('calibration.json','summary.json','confirmation.json')]
    visited=set();bindings=0
    def verify(path):
        nonlocal bindings
        path=Path(path)
        if path in visited:return
        visited.add(path)
        if path.suffix!='.json':return
        doc=json.loads(path.read_text())
        if not isinstance(doc,dict):return
        sources=doc.get('sources',{})
        if not isinstance(sources,dict):return
        for p,h in sources.items():
            if not Path(p).is_absolute():continue
            assert digest(p)==h,(path,p)
            bindings+=1;verify(p)
    for path in paths:verify(path)
    test=subprocess.run([sys.executable,'-m','unittest','test_model'],cwd=HERE,
                        capture_output=True,text=True,timeout=60)
    assert test.returncode==0,test.stdout+test.stderr
    cal,summary,confirmation=[json.loads(p.read_text()) for p in paths]
    assert summary['validation']['passed']
    assert confirmation['eligible_objects']==0 and not confirmation['passed']
    result=dict(passed=True,previous_goal_turn='progress: fragment timing and omitted-support diagnostics completed',
                verified_bindings=bindings,unique_dependencies=len(visited),new_component_tests_passed=3,
                test_output=test.stdout+test.stderr,exploratory_scale_screen_passed=True,
                independent_confirmation='unavailable: zero advancing-epoch triplets',
                causal_position_improvement_established=False,goal_status='active',
                sources={str(p):digest(p) for p in paths+[Path(__file__),HERE/'run.py',HERE/'test_model.py']})
    with (HERE.parent/'joint_receiver_association/progress-audit-19.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
