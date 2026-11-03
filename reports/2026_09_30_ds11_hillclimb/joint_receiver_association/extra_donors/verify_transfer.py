"""Check frozen-coefficient transfer, timing selection and source provenance."""
import json
from pathlib import Path
import subprocess
import sys
from context import read,digest

HERE=Path(__file__).resolve().parent


def main():
    visited=set();bindings=0
    def verify(path):
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
            bindings+=1;verify(p)
    sp=HERE/'transfer-summary.json';verify(sp);summary=read(sp)
    qualified=0;times=[]
    for i in range(4):
        tp=HERE/f'timing-{i:02d}.json';timing=read(tp)
        assert timing['selected']==max((r for r in timing['starts'] if r['qualified']),key=lambda r:r['score'])
        qualified+=sum(r['qualified'] for r in timing['starts'])
        for stage in ('timing','donor'):
            rp=HERE/f'{stage}-{i:02d}.receipt.json';verify(rp);receipt=read(rp)
            assert receipt['exit_code']==0 and receipt['elapsed_s']<90
            times.append(receipt['elapsed_s'])
        donor=read(HERE/f'donor-{i:02d}.json');numeric=read(HERE/f'numeric-{i:02d}/tracks.json')
        assert len(donor['selected_tracks'])+len(donor['excluded_tracks'])==len(numeric['tracks'])
        assert donor['original_bank_replay_maximum']<1e-8
        assert all(r['confidence']>=.9 for r in donor['selected_tracks'].values())
    wins=0;count=0
    for r in summary['recordings']:
        v=r['validation'];s=r['screen']
        calculated=sum(v['signed']['per_source'][k]>value for k,value in v['receiver']['per_source'].items())
        assert calculated==s['wins'] and len(v['receiver']['per_source'])==s['count']
        passed=calculated>s['count']/2 and all(v['signed']['score']>v[a]['score'] for a in ('receiver','elevation')) and all(v['signed']['score']>score for score in r['controls'].values())
        assert passed==s['passed'];wins+=calculated;count+=s['count']
    assert all(len(f['recordings'])==2 and f['passed'] for f in summary['families'].values())
    test=subprocess.run([sys.executable,'-m','unittest','test_policy','test_availability','test_timing'],cwd=HERE,capture_output=True,text=True,timeout=60)
    assert test.returncode==0,test.stdout+test.stderr
    result=dict(passed=True,previous_goal_turn='progress: availability-qualified numerical donor banks exported',
                verified_bindings=bindings,unique_dependencies=len(visited),component_tests_passed=6,
                test_output=test.stdout+test.stderr,qualified_timing_starts=qualified,
                source_wins=wins,source_groups=count,passed_transfer_recordings=4,
                maximum_worker_elapsed_s=max(times),causal_position_improvement_established=False,goal_status='active',
                sources={str(p):digest(p) for p in (Path(__file__),sp,HERE/'test_timing.py')})
    with (HERE.parent/'progress-audit-24.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
