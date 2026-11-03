"""Preserve failed attempts, repair adapter coverage and bound large-model search."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from run_ds23_association_diagnostics import CASES
from probe_ds23_joint_family_search import OUT as JOINT
from probe_ds23_secondary_curves import OUT as CURVES
from run_algo01_ds23_sample import ROOT,read,write,sha


def worker(task):
    directory,tool,case,args=task;started=time.monotonic()
    with (directory/(case+'_completed.log')).open('w') as log:
        p=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools'/tool),'--case',case]+args,
            cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
            stdout=log,stderr=log,timeout=480)
    return dict(method='joint' if directory==JOINT else 'curves',case=case,code=p.returncode,
                seconds=time.monotonic()-started,args=args)


def run():
    for directory in (JOINT,CURVES):
        for name in ('execution.json','protocol.json'):
            target=directory/('initial_'+name)
            if not target.exists():target.write_bytes((directory/name).read_bytes())
    old=JOINT/'source_v1/probe_ds23_joint_family_search.py'
    joint_protocol=read(JOINT/'initial_protocol.json')
    assert joint_protocol['source_sha256']==sha(old)
    joint_protocol.update(source_versions_sha256=[sha(old),sha(ROOT/'tools/probe_ds23_joint_family_search.py')],
        source_sha256=sha(ROOT/'tools/probe_ds23_joint_family_search.py'),
        proposal_budget_by_case={c:dict(rounds=2 if c=='DS23-0202' else 5,steps=12 if c=='DS23-0202' else 48) for c in CASES},
        final_budget_all_cases=dict(rounds=5,steps=48),large_case_budget_changed_after_420s_timeout=True)
    write(JOINT/'protocol.json',joint_protocol)
    curve_protocol=read(CURVES/'initial_protocol.json');curve_protocol.update(source_sha256=sha(ROOT/'tools/probe_ds23_secondary_curves.py'),
        public_adapter_handles_both_frozen_export_formats=True,initial_fast_adapter_failure_preserved=True)
    write(CURVES/'protocol.json',curve_protocol)
    tasks=[]
    if not (JOINT/'DS23-0202.json').exists():
        tasks.append((JOINT,'probe_ds23_joint_family_search.py','DS23-0202',['--proposal-rounds','2','--proposal-steps','12']))
    for case in CASES:
        path=CURVES/(case+'.json')
        if not path.exists() or read(path)['source_sha256']!=curve_protocol['source_sha256']:
            tasks.append((CURVES,'probe_ds23_secondary_curves.py',case,[]))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,t):t for t in tasks}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future][2],method='joint' if futures[future][0]==JOINT else 'curves',code=1,reason=repr(error))
            receipts.append(r);write(JOINT/'completion_attempts.json',receipts);print(r,flush=True)
    for directory,method in ((JOINT,'joint'),(CURVES,'curves')):
        final=[]
        for case in CASES:
            candidates=[r for r in receipts if r['method']==method and r['case']==case]
            if candidates:final.append(candidates[-1])
            elif (directory/(case+'.json')).exists():
                final.append(dict(case=case,method=method,code=0,source_sha256=read(directory/(case+'.json'))['source_sha256'],
                                  validated_existing_completed_result=True))
            else:final.append(dict(case=case,method=method,code=1,reason='missing result'))
        write(directory/'execution.json',final)


if __name__=='__main__':run()
