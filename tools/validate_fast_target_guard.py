"""Bounded, separate-recording test of the frozen preconstraint target guard."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from debug_fast_graph_unassociated import read,write


def target_guard(source,unconstrained):
    if source['status']!='accepted':return False
    target=source['proposal']['component']
    for arm in ('c0','fitted_c'):
        matches=[g for g in unconstrained[arm]['gates']['tracks'] if g['component']==target]
        if len(matches)!=1 or not matches[0]['compatible']:return False
    return True


def validate_members(selected,excluded):
    ids=[r['recording_id'] for r in selected]
    if len(ids)!=len(set(ids)) or set(ids)&set(excluded):raise ValueError('validation recordings must be distinct and disjoint')
    if any(r['sample_rate_hz']!=10_000_000 or r['recording_format']!='short_window_iq_recording' for r in selected):
        raise ValueError('10 MS/s fast recordings only')
    return sorted(r['dataset_label'] for r in selected)


def freeze(args):
    source=args.prepared;sample=read(source/'sample.json');old=read(args.development/'sample.json')
    cases=validate_members(sample['selected'],[r['recording_id'] for r in old['selected']])
    args.output.mkdir(parents=True,exist_ok=False);root=args.output/'inference';root.mkdir()
    shutil.copyfile(source/'sample.json',root/'sample.json');input_hashes={}
    for case in cases:
        receipt=read(source/case/'preparation_receipt.json')
        if receipt['status']!='prepared' or not receipt['no_GPS_or_previous_results'] or not receipt['all_TLEs_causal']:
            raise ValueError('qualified causal preparation required')
        for relative,digest in receipt['files_sha256'].items():
            path=source/relative
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('prepared input changed: '+relative)
            target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copyfile(path,target)
            input_hashes[relative]=digest
        shutil.copyfile(source/case/'preparation_receipt.json',root/case/'preparation_receipt.json')
    (args.output/'recovery').mkdir()
    names=('validate_fast_target_guard.py','combined_family_reentry.py','provisional_family_recovery.py',
           'algo02_scan.py','fast_graph_engine.py','benchmark_graph_covariance.py')
    write(args.output/'protocol.json',dict(cases=cases,recordings=sample['selected'],prepared_source=str(source),
        root=str(root),input_sha256=input_hashes,excluded_recording_ids=[r['recording_id'] for r in old['selected']],
        selection='all four previously prepared later fast recordings, no position-result selection',
        policy='existing accepted combined proposal AND restored target passes existing unconstrained gates in both c arms',
        proposal_unchanged='one largest eligible removed-family curve; causal catalogue agreement; held-prior selector; original final gates and old IDs preserved',
        budgets_s=dict(algo02=360,cavity=360,recovery=240),workers=4,
        paired_c=True,GPS_in_inference=False,new_RF=False,postscan_TLE=False,production_changed=False,
        source_sha256={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in names},
        qualification='separate recordings from guard development, same evaluation site; small prepared-availability cohort, not new-location validation'))


def run(args):
    protocol=read(args.output/'protocol.json');root=Path(protocol['root']);tool=Path(__file__).parent
    for name,digest in protocol['source_sha256'].items():
        if hashlib.sha256((tool/name).read_bytes()).hexdigest()!=digest:raise ValueError('frozen source changed: '+name)
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    def one(case):
        started=time.monotonic();receipt=dict(case=case,status='running',stages=[])
        stages=[('algo02',[sys.executable,str(tool/'algo02_scan.py'),'--run-dir',str(root),'--case',case,'--stage','all']),
                ('cavity',[sys.executable,str(tool/'fast_graph_engine.py'),'--root',str(root),'--case',case]),
                ('recovery',[sys.executable,str(tool/'combined_family_reentry.py'),'case','--root',str(root),'--case',case,'--output',str(args.output/'recovery'/case)])]
        try:
            for name,command in stages:
                mark=time.monotonic()
                with (args.output/(case+'-'+name+'.log')).open('x') as log:
                    child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    try:code=child.wait(timeout=protocol['budgets_s'][name])
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGTERM)
                        try:child.wait(timeout=3)
                        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                        raise TimeoutError(name+' bounded deadline')
                receipt['stages'].append(dict(stage=name,returncode=code,seconds=time.monotonic()-mark))
                if code:raise RuntimeError(name+' failed')
                if name=='algo02' and read(root/case/'algo02_result.json')['status']!='accepted':raise ValueError('unqualified paired baseline')
                if name=='cavity' and read(root/'family_cavity/position'/(case+'.json'))['status']!='complete':raise ValueError('incomplete family baseline')
            source=read(args.output/'recovery'/case/'result.json')
            unconstrained=read(args.output/'recovery'/case/'unconstrained.json') if source['status']=='accepted' else None
            accepted=target_guard(source,unconstrained)
            proposed=[]
            if source['status']=='accepted' and not accepted:
                # Full observation identity is already retained in original
                # proposal gate receipts; avoid depending on graph JSON shape.
                gate=next(g for g in source['proposal_pair']['c0']['gates']['tracks'] if g['component']==source['proposal']['component'])
                proposed=gate['observation_ids']
            receipt.update(status='complete',reentry_status=source['status'],guard_accepted=accepted,
                policy=source['policy'] if accepted else source['support'],provisional_observation_ids=proposed)
        except Exception as exc:
            receipt.update(status='failed',reason=repr(exc))
        receipt['seconds']=time.monotonic()-started;write(args.output/(case+'-terminal.json'),receipt)
        return dict(case=case,status=receipt['status'],seconds=receipt['seconds'],reason=receipt.get('reason'),guard_accepted=receipt.get('guard_accepted'))
    rows=[]
    with ThreadPoolExecutor(max_workers=protocol['workers']) as pool:
        for future in as_completed([pool.submit(one,c) for c in protocol['cases']]):
            row=future.result();rows.append(row);print(row,flush=True)
    write(args.output/'execution.json',rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['freeze','run'])
    p.add_argument('--prepared',type=Path);p.add_argument('--development',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();freeze(a) if a.mode=='freeze' else run(a)
