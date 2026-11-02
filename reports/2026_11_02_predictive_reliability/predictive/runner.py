"""Prepare fixed splits without fitting; run only after parent protocol sealing.

Prepare roster: {cases:[{case,input_path,family,seed}]}. Run protocol requires
predictive.plan_sha256 and source_sha256; other policy fields live in the parent
protocol. Preparation and execution each have a separate120s preload window
(60s per case), then execution has a600s fit window with120s cells and4 workers.
All workers are terminated and joined on the overall deadline; no retry loop.
"""
import argparse
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import signal
import time
import traceback
import numpy as np
import engine as numerical
from algo07_science import engine as e
from algo07_science.validation import clean

ROOT=Path(__file__).resolve().parent
CONTEXTS={}
FIT_BUDGET=dict(max_rounds=15,maxiter=25,maxfun=100)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):return json.loads(Path(path).read_text())


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(clean(value),indent=2,allow_nan=False)+'\n');tmp.replace(path)


def timeout(*_):raise TimeoutError('Bounded predictive computation deadline')


def preload(rows):
    began=time.monotonic();deadline=began+120.;loaded={};receipts={}
    previous=signal.signal(signal.SIGALRM,timeout)
    try:
        for row in rows:
            case=row['case'];tic=time.monotonic();remaining=deadline-tic
            if remaining<=0:receipts[case]=dict(status='preload_total_deadline');continue
            try:
                path=Path(row['input_path']);digest=sha(path)
                if row.get('input_sha256')and digest!=row['input_sha256']:raise ValueError('Frozen input hash changed')
                signal.alarm(max(1,math.ceil(min(60.,remaining))))
                e.configure(path.parent.parent,ROOT/'local_engine');e.ROOTS[case[:4]]=path.parent.parent
                d,z,replay=e.load_case(case)
                signal.alarm(0);loaded[case]=(d,z)
                receipts[case]=dict(status='loaded',seconds=time.monotonic()-tic,input_sha256=digest,
                    context_inventory=numerical.adapter.context_inventory(d),replay=replay)
            except Exception as exc:
                signal.alarm(0);receipts[case]=dict(status='preload_failed',seconds=time.monotonic()-tic,error=repr(exc),traceback=traceback.format_exc())
    finally:signal.alarm(0);signal.signal(signal.SIGALRM,previous)
    return loaded,dict(seconds=time.monotonic()-began,total_window_seconds=120,per_case_seconds=60,cases=receipts)


def prepare(roster,output):
    rows=read(roster)['cases'];loaded,receipt=preload(rows);plans=[]
    for row in rows:
        case=row['case'];record=dict(row,input_sha256=sha(row['input_path']))
        if case not in loaded:record.update(status='preload_unavailable',partitions=[],preload=receipt['cases'][case])
        else:
            d,z=loaded[case];base=d['problems']['fitted_c'][0]
            ids=numerical.native(base)['ids'];assert np.array_equal(ids,numerical.native(d['problems']['c0'][0])['ids'])
            record.update(status='prepared',partitions=numerical.plans(base,int(row['family']),int(row['seed'])),
                context_inventory=receipt['cases'][case]['context_inventory'])
        plans.append(record)
    write(output,dict(cases=plans,preparation=receipt,no_candidate_fits=True,
        grouping='Three synchronized5s random20% group folds, adjacent5s guard, plus two target-family-to-receiver transfers'))
    print(json.dumps(dict(plan=str(output),sha256=sha(output),prepared=sum(r['status']=='prepared'for r in plans),seconds=receipt['seconds'])),flush=True)


def label(spec):return f"{spec['case']}_{spec['split']['name']}_{spec['arm']}_SD{spec['scale']:g}"


def work(spec):
    path=ROOT/'cells'/(label(spec)+'.json');began=time.monotonic()
    common=dict(case=spec['case'],split=spec['split']['name'],kind=spec['split']['kind'],arm=spec['arm'],SD_scale=spec['scale'],
        target_family=spec['family'],protocol_sha256=spec['protocol_sha256'])
    if not spec['split']['eligible']:
        row=dict(common,status='ineligible_support',support_reasons=spec['split'].get('ineligible_reasons',[]),numerical_fit_qualified=False)
        write(path,row);return row
    write(path,dict(common,status='running',started_monotonic=began))
    previous=signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    try:
        d,z=CONTEXTS[spec['case']]
        row=numerical.evaluate(d,z,spec['arm'],spec['scale'],spec['family'],spec['split'],FIT_BUDGET)
        row.update(common)
    except Exception as exc:
        row=dict(common,status='cell_timeout'if isinstance(exc,TimeoutError)else'failed',numerical_fit_qualified=False,
            error=repr(exc),traceback=traceback.format_exc())
    finally:signal.alarm(0);signal.signal(signal.SIGALRM,previous)
    row['wall_seconds']=time.monotonic()-began;write(path,row)
    print(label(spec),row['status'],row.get('numerical_fit_qualified'),flush=True)
    return row


def run(protocol_path,plan_path):
    global CONTEXTS
    protocol=read(protocol_path);configuration=protocol['predictive']
    if sha(plan_path)!=configuration['plan_sha256']:raise ValueError('Frozen split plan hash mismatch')
    if not protocol.get('source_sha256'):raise ValueError('Parent source hash seal required before fitting')
    for path,digest in protocol['source_sha256'].items():
        if sha(path)!=digest:raise ValueError('Frozen source changed: '+path)
    plan=read(plan_path);CONTEXTS,preload_receipt=preload(plan['cases'])
    write(ROOT/'execution_preload.json',preload_receipt)
    digest=sha(protocol_path);specs=[];terminal=[]
    for row in plan['cases']:
        if row['case']not in CONTEXTS or row.get('status')!='prepared':
            terminal.append(dict(case=row['case'],status='preload_unavailable',numerical_fit_qualified=False));continue
        for split in row['partitions']:
            for arm in ['c0','fitted_c']:
                for scale in [1.,4.]:specs.append(dict(case=row['case'],family=int(row['family']),split=split,arm=arm,scale=scale,protocol_sha256=digest))
    began=time.monotonic();deadline=began+600.;pool=multiprocessing.get_context('fork').Pool(processes=4)
    futures=[pool.apply_async(work,(spec,))for spec in specs];terminated=False
    try:
        pool.close()
        for future in futures:
            remaining=deadline-time.monotonic()
            if remaining<=0:terminated=True;break
            try:future.get(timeout=remaining)
            except multiprocessing.TimeoutError:terminated=True;break
    finally:
        if terminated:pool.terminate()
        pool.join()
    for spec in specs:
        path=ROOT/'cells'/(label(spec)+'.json')
        if path.exists()and read(path).get('status')not in ('running',):row=read(path)
        else:
            row=dict(case=spec['case'],split=spec['split']['name'],kind=spec['split']['kind'],arm=spec['arm'],SD_scale=spec['scale'],
                status='incomplete_at_fit_deadline',numerical_fit_qualified=False,protocol_sha256=digest)
            write(path,row)
        terminal.append(row)
    write(ROOT/'results.json',dict(protocol_sha256=digest,plan_sha256=sha(plan_path),preload=preload_receipt,
        fit_window_seconds=600,fit_seconds=time.monotonic()-began,workers_terminated_at_deadline=terminated,all_workers_joined=True,rows=terminal))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-roster',type=Path);parser.add_argument('--output-plan',type=Path,default=ROOT/'plan.json')
    parser.add_argument('--run',action='store_true');parser.add_argument('--protocol',type=Path);parser.add_argument('--plan',type=Path,default=ROOT/'plan.json');args=parser.parse_args()
    if args.prepare_roster:prepare(args.prepare_roster,args.output_plan)
    elif args.run and args.protocol:run(args.protocol,args.plan)
    else:parser.error('Choose --prepare-roster or --run --protocol')
