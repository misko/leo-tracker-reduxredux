"""Source-frozen, bounded fixed-state branch-mass diagnostic on nine windows."""
import time
START=time.monotonic()
import argparse
import fcntl
import os
from pathlib import Path
import sys
import numpy as np
from run_shared_visibility_pilot import HERE,ROOT,sealed,baseline,setup,digest,verify_sources,save,execute
from association_mass import summarize_scores

UNITS=tuple(f'{ds}-B01-{suffix}' for ds in ['DS9','DS10','DS11'] for suffix in ['S1','D1','Q'])
OUT=HERE/'association-ambiguity-v1'


def source(unit):
    arm='shared-curvature-pilot-v1' if unit.endswith('S1') else 'shared-window-pilot-v1'
    directory=HERE/arm/unit;path=directory/(unit+'.json');receipt=sealed(path)
    audit=sealed(directory/'evaluation.json');launch=sealed(path.with_suffix('.launch.json'))
    audit_launch=sealed(directory/'audit-launch.json');frozen=sealed(directory/'sources.json')
    if not (audit['accepted'] and all(audit['checks'].values()) and audit_launch['returncode']==0
            and audit_launch['within_budget'] and not audit_launch['timed_out']
            and launch['receipt_sha256']==digest(path) and launch['freeze_sha256']==digest(directory/'sources.json')):
        raise ValueError('unaccepted or unbound source')
    verify_sources(receipt['source_sha256']);verify_sources(receipt['inputs'])
    verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    return receipt,{str(p):digest(p) for p in [path,path.with_suffix('.launch.json'),directory/'sources.json',directory/'evaluation.json',directory/'audit-launch.json']}


def worker(unit):
    frozen=sealed(OUT/'sources.json');verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    receipt,_=source(unit);original,_,_=baseline(unit);model=setup(unit,original)
    state=np.asarray(receipt['best']['mean']);value,_,labels=model.evaluate(state,gradient=False)
    assert list(labels)==receipt['best']['associations'] and abs(value-receipt['best']['objectives'][-1])<1e-7
    rows=[]
    for i,(port,columns,label) in enumerate(zip(model.ports,model.columns,labels,strict=True)):
        result=summarize_scores(port.score_all(state[columns]))
        assert result['top_index']==label and abs(result['mass_sum']-1)<1e-12
        rows.append(dict(track=i,observation_ids=list(port.observation_ids),**result))
    verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    save(OUT/(unit+'.json'),dict(unit=unit,size=original['binding']['size'],rows=rows,seconds=time.monotonic()-START,
        source_receipt_sha256=digest(next(Path(p) for p in frozen['inputs'] if p.endswith('/'+unit+'.json'))),
        freeze_sha256=digest(OUT/'sources.json'),qualification='Conditional plug-in branch mass at fitted nuisance values; no refitting or geographic reference.'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',choices=UNITS);args=parser.parse_args()
    if args.worker:worker(args.worker);return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        inputs={}
        for unit in UNITS:inputs.update(source(unit)[1])
        sources={str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
        for name in ['ASSOCIATION_AMBIGUITY_PLAN.md','test_association_mass.py']:
            p=HERE/name;sources[str(p)]=digest(p)
        OUT.mkdir(exist_ok=False)
        save(OUT/'sources.json',dict(inputs=inputs,source_sha256=sources,units=UNITS))
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(ROOT/'src'))
        for unit in UNITS:
            launch=execute([sys.executable,str(Path(__file__).resolve()),'--worker',unit],OUT,unit,timeout_s=120.,env=env)
            path=OUT/(unit+'.json');launch['receipt_sha256']=digest(path) if path.exists() else None
            save(path.with_suffix('.launch.json'),launch)
            print(unit,launch['returncode'],round(launch['elapsed_seconds'],2),flush=True)


if __name__=='__main__':main()
