"""Bounded same-scan baseline/challenger pairs for disjoint index workers."""
import json
from pathlib import Path
import subprocess
import sys
import time

import additional_fit as runner
import harness


def attempt(index,challenger):
    family,variant='source_balance','source_receiver_equal'
    folder=(runner.HERE/family/'runs'/'additional') if challenger else runner.ADDITIONAL/'runs'
    folder.mkdir(parents=True,exist_ok=True)
    base=folder/(f'{variant}_{index:02d}' if challenger else f'{index:02d}_iid')
    receipt=base.with_suffix('.receipt.json')
    if receipt.exists():
        return
    if base.with_suffix('.json').exists() or base.with_suffix('.log').exists():
        raise RuntimeError('Unreceipted attempt requires process audit')
    args=['challenger',family,variant,str(index)] if challenger else ['baseline',str(index)]
    command=['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1',
             'timeout','--kill-after=5s','90s','nice','-n','19',harness.PYTHON,
             str(runner.HERE/'additional_fit.py'),*args]
    started=time.monotonic()
    with base.with_suffix('.log').open('x') as stream:
        result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
    row=dict(index=index,exit_code=result.returncode,wall_s=time.monotonic()-started,
             command=command,coordinator_sha256=harness.digest(__file__))
    if challenger:
        row.update(family=family,variant=variant)
    with receipt.open('x') as stream:
        json.dump(row,stream,indent=2)
    print(json.dumps(row),flush=True)


if __name__=='__main__':
    indices=[int(value) for value in sys.argv[1].split(',')]
    plan=json.loads((runner.ADDITIONAL/'plan.json').read_text())
    assert len(set(indices))==len(indices) and all(0<=i<len(plan['inputs']) for i in indices)
    for index in indices:
        attempt(index,False)
        attempt(index,True)
