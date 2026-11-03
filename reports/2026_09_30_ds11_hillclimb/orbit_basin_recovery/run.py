"""Reuse the frozen original-IID basin recovery with new source-bound seeds."""
import importlib.util
from pathlib import Path
import sys
import json

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
spec=importlib.util.spec_from_file_location('frozen_basin_recovery',HILL/'drift_basin_recovery/run.py')
recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)
recovery.HERE=HERE
read,write,digest=recovery.read,recovery.write,recovery.digest

def prepare():
    prior_plan=HILL/'joint_orbit_position/plan.json';prior_selection=HILL/'joint_orbit_position/selections.json'
    p=read(prior_plan);recovery.parent.verify(p);s=read(prior_selection)
    assert s['plan_sha256']==digest(prior_plan)
    base=HILL.parent/'2026_09_30_ds11_single10/plan.json';original=read(base)
    sources=dict(p['sources'])
    for path in (prior_plan,prior_selection,base,HILL/'drift_basin_recovery/run.py',
                 HILL/'drift_basin_recovery/test_run.py',Path(__file__),HERE/'test_run.py',HERE/'PROTOCOL.md'):
        sources[str(path)]=digest(path)
    scans={index:dict(input=original['inputs'][int(index)],control=row['control']) for index,row in p['scans'].items()}
    jobs=recovery.deduplicate(s['attempts'])
    write(HERE/'plan.json',dict(config=original['config'],scans=scans,jobs=jobs,sources=sources,reference_used=False))
    print(json.dumps(dict(jobs=len(jobs),plan_sha256=digest(HERE/'plan.json'))))

if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    elif sys.argv[1]=='fit':recovery.fit(int(sys.argv[2]))
    else:dict(batch=recovery.batch,seal=recovery.seal,assess=recovery.assess)[sys.argv[1]]()
