"""Clarify existing accuracy tradeoffs; never replace the failed replication gate."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from model import summarize

HERE=Path(__file__).resolve().parent;HILL=HERE.parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'model.py',HERE/'test_model.py')}
    panels={};all_rows=[];verified=0
    for name,filename in [('original32','policy-original32-audited.json'),('additional12','policy-additional12-audited.json')]:
        path=HILL/filename;doc=json.loads(path.read_text());sources[str(path)]=digest(path)
        for p,h in doc['source_sha256'].items():assert digest(p)==h,p;verified+=1
        if name=='additional12':assert doc['additional_replication_passed'] is False
        else:assert doc['additional_replication_passed'] is None
        panels[name]=summarize(doc['rows']);all_rows.extend(doc['rows'])
    panels['pooled44']=summarize(all_rows)
    assert panels['original32']['attempts']==32 and panels['additional12']['attempts']==12
    test=subprocess.run([sys.executable,'-m','unittest','test_model'],cwd=HERE,capture_output=True,text=True,timeout=60)
    assert test.returncode==0,test.stdout+test.stderr
    result=dict(policy='qualified source_receiver_equal else qualified original IID',panels=panels,
                original_policy_source_bindings_verified=verified,component_tests_passed=2,test_output=test.stdout+test.stderr,
                additional_replication_passed=False,promotion_justified=False,
                interpretation='Pooled exposed-site metrics do not supersede worse separate-record results or missing coverage.',sources=sources)
    with (HERE/'summary.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    audit=dict(passed=True,previous_goal_turn='progress: complete six-record 2.5MS/s position pilot failed both family gates',
               source_bindings_verified=verified,component_tests_passed=2,additional_replication_passed=False,
               promotion_justified=False,goal_status='active',sources={str(HERE/'summary.json'):digest(HERE/'summary.json')})
    with (HILL/'joint_receiver_association/progress-audit-26.json').open('x') as f:json.dump(audit,f,indent=2)
    print(json.dumps(panels,indent=2))


if __name__=='__main__':main()
