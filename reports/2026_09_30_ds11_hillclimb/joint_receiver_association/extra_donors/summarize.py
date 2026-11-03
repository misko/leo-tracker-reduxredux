"""Verify bounded donor eligibility, retaining unresolved calibration needs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'test_policy.py')};rows=[]
    for i in range(4):
        path=HERE/f'capture-{i:02d}.json';rp=HERE/f'capture-{i:02d}.receipt.json'
        receipt=json.loads(rp.read_text());assert receipt['exit_code']==0
        doc=json.loads(path.read_text())
        for bound in (doc,receipt):
            for p,h in bound['sources'].items():assert digest(p)==h,(path,p)
        sources.update({str(p):digest(p) for p in (path,rp)})
        assert doc['family'] in (0,1)
        rows.append({k:doc[k] for k in ('ordinal','session_id','family','retained_tracks','tracks_by_receiver','input_manifest_sha256','analysis_manifest_sha256')})
        rows[-1]['worker_elapsed_s']=receipt['elapsed_s']
    test=subprocess.run([sys.executable,'-m','unittest','test_policy'],cwd=HERE,capture_output=True,text=True,timeout=60)
    assert test.returncode==0,test.stdout+test.stderr
    out=dict(rows=rows,new_component_tests_passed=2,test_output=test.stdout+test.stderr,
             matched_settings={str(f):sum(r['family']==f for r in rows) for f in (0,1)},
             unresolved=['exact causal orbit support','analysis availability before DS11','inferred source labels and geometry','independent receiver calibration transfer'],
             calibration_ready=False,causal_position_improvement_established=False,sources=sources)
    with (HERE/'summary.json').open('x') as f:json.dump(out,f,indent=2)
    audit=dict(passed=True,previous_goal_turn='progress: fixed-height implementation and real-data parity completed',
               successful_capture_checks=4,new_component_tests_passed=2,goal_status='active',
               causal_position_improvement_established=False,sources={str(HERE/'summary.json'):digest(HERE/'summary.json')})
    with (HERE.parent/'progress-audit-22.json').open('x') as f:json.dump(audit,f,indent=2)
    print(json.dumps({k:v for k,v in out.items() if k not in ('sources','rows')},indent=2))


if __name__=='__main__':main()
