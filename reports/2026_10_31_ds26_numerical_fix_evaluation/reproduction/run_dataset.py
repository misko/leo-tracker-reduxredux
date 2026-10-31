"""Frozen DS26 schedule replay. Scientific inference never reads evaluation truth."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
REPO = Path('/srv/bulk/leo-dev/fast-algo02-production-v1')
SOURCE = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030')

def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f: json.dump(value, f, indent=2, allow_nan=False)

def overflow(value):
    if isinstance(value, dict):
        return value.get('phase_outside_reference_window') is True or any(overflow(v) for v in value.values())
    return isinstance(value, list) and any(overflow(v) for v in value)

def owner_map(terminal, arm):
    if terminal.get('selected'): return terminal['selected']['arms'][arm]['owners']
    support = terminal.get('source_support')
    if support: return support[arm]['owners']
    raise ValueError('Missing incumbent ownership proof')

def additive_gate(terminal, result):
    if not result.get('selected'): return False, 'no_RF_qualified_replay_candidate'
    if not (terminal.get('read_audit') or {}).get('verified'):
        return False, 'historical_production_read_audit_not_verified'
    for arm in ('c0','fitted_c'):
        old = owner_map(terminal, arm); new = result['selected']['arms'][arm]['owners']
        if any(new.get(o) != n for o,n in old.items()):
            return False, 'would_lose_or_change_current_ALGO03_owner'
    return True, 'paired_RF_qualified_and_preserves_current_ALGO03_owners'

def one(case):
    import algo03_shadow_worker as worker
    from leo.application.automatic_fast_graph import execute
    src = SOURCE/'cases'/case/'candidate-v2/recovery'
    out = ROOT/'cases'/case; out.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    terminal_path = src.parent/'terminal.json'
    if not terminal_path.exists() or not (src/'decision.json').exists():
        write(out/'receipt.json',dict(case=case,state='unavailable',reason='original_ALGO03_unavailable'))
        return
    original = read(src/'decision.json'); terminal = read(terminal_path)
    descriptor = read(src/'snapshot/descriptor.json')
    write(out/'snapshot/descriptor.json',descriptor)
    completed = {a['track_id'] for a in original['attempts'] if (src/a['track_id']/'annotation/result.json').exists()}
    receipts = []; charged = 0.; originals = {s['name']:s for s in original['stages']}
    dependency_hashes = {str(p):sha(p) for p in (src/'decision.json',terminal_path,src/'snapshot/descriptor.json')}
    write(out/'protocol.json',dict(case=case,source=str(src),source_hashes=dependency_hashes,
        completed_target_ids=sorted(completed),original_attempts=original['attempts'],
        scope='cached conditional replay of original completed target schedule and frozen nominations',
        same_candidate_alias_partition_inputs=True,no_GPS_inference=True,causal_bank_unchanged=True,
        reference_limit_s=30,centered_gradient_step_km=.001,maxls=40,maxiter=48,
        total_objective_calls_per_round=240,phase_rounds=5,
        old_stage_time_charged_for_reused_stages=True,maximum_seconds=original['maximum_seconds'],
        acceptance='original physical checks plus preservation of current published ALGO03 owners',
        production_read_audit_failures_remain_fallback=True))
    original_select=worker.select_targets
    def select(inv,limit=8):
        rows,count=original_select(inv,limit)
        return [r for r in rows if r['track_id'] in completed],count
    worker.select_targets=select

    def copy_tree(source,dest):
        for p in sorted(source.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts: continue
            q=dest/p.relative_to(source); q.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,q)
            dependency_hashes[str(p)] = sha(p)

    def staged(command, *, log, timeout):
        nonlocal charged
        script=Path(command[2]).name; args=command[3:]
        opts=lambda name: Path(args[args.index(name)+1])
        stage_name=Path(log.name).stem
        dest=opts('--output'); relative=dest.relative_to(out); old=src/relative
        reuse=False; reason='numerical_dependency_changed'; annotation_changed=False
        if script=='algo03_inventory.py': reuse=True; reason='graph_and_original_baseline_unchanged'
        elif script=='annotate_predictive_only.py':
            reuse=not overflow(read(old/'result.json'))
            reason='all_saved_training_phase_updates_within_15s' if reuse else 'saved_training_phase_clipped'
        elif script=='include_predictive_annotations.py':
            validation=opts('--validation')
            annotation_changed=bool(read(validation/'protocol.json').get('numerical_replay'))
            reuse=(old/'control.json').exists() and not annotation_changed
            if reuse:
                reuse=not any(overflow(read(p)) for p in old.glob('*.json'))
            reason='shared_fit_has_no_changed_numerical_dependency' if reuse else reason
        elif script=='audit_shared_predictive_inclusion.py':
            trial=opts('--trial')
            reuse=any(r['script']=='include_predictive_annotations.py' and r['output']==str(trial) and r['reused'] for r in receipts)
            reason='unchanged_shared_fit_exact_replay'
        record=dict(script=script,output=str(dest),source=str(old),reused=reuse,reason=reason)
        started=time.monotonic()
        if reuse:
            if old.is_dir(): copy_tree(old,dest)
            else:
                # A reused whole trial already contains its immutable exact audit.
                if not dest.exists(): dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(old,dest)
                dependency_hashes[str(old)]=sha(old)
            charge=originals.get(stage_name,{}).get('seconds',0.)
            charged+=max(0.,charge-(time.monotonic()-started))
            code=0; record['charged_original_seconds']=charge
        else:
            if script=='annotate_predictive_only.py':
                cmd=[sys.executable,'-B',str(ROOT/'annotation_replay.py'),'--inventory',str(opts('--inventory')),
                     '--source',str(old),'--output',str(dest)]
            else:
                cmd=[sys.executable,'-B',str(ROOT/'numerical_stage.py'),'--reference-limit-s','30',
                     '--centered-lbfgsb','--receipt',str(out/'numerical-receipts'/(stage_name+'.json')),
                     str(REPO/'tools'/script),*args]
            record['command']=cmd
            code=execute(cmd,log=log,timeout=timeout)
        record.update(returncode=code,wall_seconds=time.monotonic()-started)
        receipts.append(record)
        write(out/'stage-cache'/f'{len(receipts):03d}.json',record)
        return code
    worker.execute=staged
    worker.time=SimpleNamespace(monotonic=lambda:time.monotonic()+charged)
    result=worker.run(out,original['maximum_seconds'])
    # This is a research replay; never fabricate the production OS read-audit.
    accepted,reason=additive_gate(terminal,result)
    chosen=result['selected'] if accepted else terminal.get('selected')
    state='replay_failed' if result.get('failure') else 'complete'
    write(out/'outcome.json',dict(case=case,state=state,accepted_update=accepted,reason=reason,
        baseline_terminal=str(terminal_path),baseline_sha256=sha(terminal_path),selected=chosen,
        baseline=terminal['baseline'],candidate_decision=result['decision'],
        production_changed=False,research_only=True,production_read_guard_rerun=False,
        same_original_GLRT=True,causal_only=True,no_GPS_inference=True,
        replay_failure=result.get('failure'),stages=receipts,wall_seconds=time.monotonic()-began,
        charged_cached_seconds=charged))
    files=[out/'outcome.json',out/'decision.json',out/'protocol.json']
    write(out/'inference-seal.json',dict(source_hashes=dependency_hashes,
          output_hashes={str(p):sha(p) for p in files},no_GPS_inference=True))
    write(out/'receipt.json',dict(case=case,state=state,accepted_update=accepted,reason=reason,
        seconds=time.monotonic()-began))

def batch(workers,cases=None):
    manifest=read(SOURCE/'datasets/DS26.json')
    members=[c for c in manifest['cases'] if c['recording_format']=='short_window_iq_recording']
    if cases: members=[c for c in members if c['case'] in cases]
    protocol=ROOT/'dataset-protocol.json'
    if not protocol.exists():
        write(protocol,dict(source_manifest=str(SOURCE/'datasets/DS26.json'),manifest_sha256=sha(SOURCE/'datasets/DS26.json'),
            fast_cases=[c['case'] for c in manifest['cases'] if c['recording_format']=='short_window_iq_recording'],
            no_adaptive=True,workers=workers,threads=1,supervisor_case_cap_s=1230,
            no_new_RF=True,no_future_TLE=True,no_GPS_inference=True,conditional_cached_replay=True))
    def work(c):
        out=ROOT/'cases'/c['case']
        if (out/'receipt.json').exists(): return read(out/'receipt.json')
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
            PYTHONPATH=os.pathsep.join(map(str,[REPO/'src',REPO/'tools',ROOT])))
        cmd=[sys.executable,'-B',__file__,'one','--case',c['case']]
        with (ROOT/(c['case']+'.log')).open('x') as log:
            p=subprocess.Popen(cmd,env=env,cwd=REPO,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try: code=p.wait(timeout=1230)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGTERM)
                try: code=p.wait(timeout=12)
                except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL);code=p.wait()
        if not (out/'receipt.json').exists():
            write(out/'receipt.json',dict(case=c['case'],state='replay_failed',returncode=code,baseline_fallback=True))
        return read(out/'receipt.json')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for f in as_completed([pool.submit(work,c) for c in members]):print(json.dumps(f.result()),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['one','batch']);p.add_argument('--case');p.add_argument('--cases',nargs='+');p.add_argument('--workers',type=int,default=16);a=p.parse_args()
    if a.mode=='one': one(a.case)
    else: batch(a.workers,a.cases)
