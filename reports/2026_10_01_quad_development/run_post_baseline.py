"""Run fixed diagnostic variants after the identified baseline supervisor exits."""
import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import sys
from build_selection import digest

HERE=Path(__file__).resolve().parent
CONTINUATION='continue_window.py'
PAIR_UNITS=['DS9-B01-D1','DS10-B01-D1','DS11-B01-D1','DS9-B03-D2']
BLAS_UNITS=['DS9-B01-S1','DS9-B01-D1','DS9-B01-Q']


def sealed(path):
    assert digest(path)==path.with_suffix('.sha256').read_text().strip()
    return json.loads(path.read_text())


def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--wait-pid',type=int,required=True)
    args=parser.parse_args();directory=HERE/'post-baseline-v1';directory.mkdir(exist_ok=False)
    selection=sealed(HERE/'selection.json')
    scripts=[CONTINUATION,'run_constituent_pair.py','run_constituent_pair_v2.py',
             'evaluate_variant.py','check_cold_blas.py','run_blas_window.py',
             'acquire_blas.py','acquisition_blas.py','CONSTITUENT_START_PLAN.md']
    frozen={str(HERE/name):digest(HERE/name) for name in scripts}
    frozen[str(Path(__file__).resolve())]=digest(__file__)
    save(directory/'plan.json',dict(selection_sha256=digest(HERE/'selection.json'),source_sha256=frozen,
        pair_units=PAIR_UNITS,blas_units=BLAS_UNITS,
        continuation_rule='Each unresolved iteration-limited baseline winner with at least10s remaining. Reuse already sealed diagnostics; never replace baseline.',
        qualification='Sequential bounded experiments after complete baseline audit; independent of geographic errors. DS9-B03-D2 remains explicitly failure-selected.'))
    descriptor=os.pidfd_open(args.wait_pid)
    try:
        command=[p.decode() for p in (Path('/proc')/str(args.wait_pid)/'cmdline').read_bytes().split(b'\0') if p]
        assert any(Path(p).name=='finish_baseline_queue.py' for p in command), 'unexpected supervisor'
        print(json.dumps(dict(stage='waiting_for_baseline',pid=args.wait_pid)),flush=True)
        poller=select.poll();poller.register(descriptor,select.POLLIN)
        while not poller.poll(30000):pass
    finally:os.close(descriptor)
    for path,expected in frozen.items():assert digest(path)==expected, 'planned source changed'
    rows={};inputs={}
    for block in dict.fromkeys(u['block_id'] for u in selection['evaluation_units']):
        path=HERE/'independent-v2'/block/'evaluation.json';evaluation=sealed(path)
        planned={u['unit_id'] for u in selection['evaluation_units'] if u['block_id']==block}
        assert len(evaluation['rows'])==7 and {r['unit'] for r in evaluation['rows']}==planned
        rows.update({r['unit']:r for r in evaluation['rows']});inputs[str(path)]=digest(path)
    assert len(rows)==112
    eligibility=[]
    for unit,row in rows.items():
        decision=dict(unit=unit,eligible=False,reason='baseline_accepted' if row['accepted'] else 'not_iteration_limited')
        if not row['accepted']:
            path=HERE/'independent-v2'/row['block_id']/(unit+'.json')
            if path.exists():
                receipt=sealed(path);assert digest(path)==row['receipt_sha256']
                if receipt['status']=='unresolved' and receipt.get('best') and receipt['best']['reason']=='iteration_limit':
                    remaining=90*row['size']-row['runtime_s']
                    decision.update(eligible=remaining>=10,reason='iteration_limit' if remaining>=10 else 'insufficient_remaining_budget',remaining_s=remaining)
        eligibility.append(decision)
    save(directory/'eligibility.json',dict(rows=eligibility,baseline_evaluation_sha256=inputs))
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(HERE.parents[1]/'src'))
    def run(script,unit,arm,timeout):
        for path,expected in frozen.items():assert digest(path)==expected
        target=HERE/arm/unit
        if target.exists():
            evaluation=sealed(target/'evaluation.json')
            assert len(evaluation['rows'])==1 and evaluation['rows'][0]['unit']==unit
            print(json.dumps(dict(stage='reuse_sealed',arm=arm,unit=unit)),flush=True)
            return
        print(json.dumps(dict(stage='start',arm=arm,unit=unit)),flush=True)
        with (directory/(arm+'-'+unit+'.log')).open('x') as log:
            subprocess.run([sys.executable,str(HERE/script),unit],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=timeout)
        result=sealed(target/'evaluation.json')
        print(json.dumps(dict(stage='audited',arm=arm,rows=result['rows'])),flush=True)
    for row in eligibility:
        if row['eligible']:run(CONTINUATION,row['unit'],'continuation-v1',180)
    for unit in PAIR_UNITS:run('run_constituent_pair_v2.py',unit,'constituent-pair-v2',300)
    for unit in BLAS_UNITS:run('check_cold_blas.py',unit,'cold-blas-v1',480)
    save(directory/'complete.json',dict(baseline_units=112,continuation_eligible=sum(r['eligible'] for r in eligibility),
        pair_units=PAIR_UNITS,blas_units=BLAS_UNITS,qualification='All scheduled experiments returned and have sealed evaluations; this marker does not assert scientific success.'))


if __name__=='__main__':main()
