"""Verify this experiment's recursive source bindings and component tests."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    visited=set();bindings=0;hashes={}
    def check(path):
        nonlocal bindings
        path=Path(path)
        if path in visited:return
        visited.add(path)
        if path.suffix!='.json':return
        doc=json.loads(path.read_text())
        if not isinstance(doc,dict):return
        sources=doc.get('sources',{})
        if not isinstance(sources,dict):return
        for name,expected in sources.items():
            if not Path(name).is_absolute():continue
            actual=hashes.setdefault(name,digest(name))
            assert actual==expected,(path,name)
            bindings+=1;check(name)
    for name in ('calibration.json','summary.json'):check(HERE/name)
    process=subprocess.run([sys.executable,'-m','unittest','test_model'],cwd=HERE,
                           capture_output=True,text=True,timeout=60)
    assert process.returncode==0,process.stdout+process.stderr
    summary=json.loads((HERE/'summary.json').read_text())
    assert not summary['passed']
    assert summary['threshold_us']>summary['validation']['period_us']*.01
    assert summary['summaries'][1]['median_hit_fraction']<.8
    result=dict(passed=True,previous_goal_turn='progress: historical forecast gate and provenance audit completed',
                bindings=bindings,unique_sources=len(hashes),new_component_tests_passed=3,
                test_output=process.stdout+process.stderr,
                phase_gap_qualified_groups=sum(r['qualified'] for r in summary['summaries']),
                feasibility_gate_passed=False,causal_position_improvement_established=False,
                goal_status='active',sources={str(p):digest(p) for p in
                 (Path(__file__),HERE/'test_model.py',HERE/'summary.json')})
    with (HERE.parent/'progress-audit-17.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
