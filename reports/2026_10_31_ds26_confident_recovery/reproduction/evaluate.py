"""Frozen DS27 recovery variants evaluated against the sealed DS26 ALGO04 replay.

No geographic truth is read. One qualified trial is selected per scan; independent
trials are never unioned. All unavailable and ineligible cases remain in roster.
"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

STUDY=Path(__file__).resolve().parent
BASE=Path('/srv/bulk/leo/research/ds26-numerical-dataset-20261031')
PRIOR=Path('/srv/bulk/leo/research/ds27-confident-recovery-20261031')
RELEASE=Path('/opt/leo-fast-graph/f9e262f96b6e2e75b397f69d50a0ea9104e293ef')
MODES=('marginal','conditional','conditional_feasible')
ORDER=('conditional','gap_default','gap_conditional','conditional_feasible','marginal')
sys.path.insert(0,str(PRIOR))
from qualification import qualify

def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n');q.replace(p)

def selected_trial(rows):
    valid=[r for r in rows if r['qualification']['qualified']]
    # Same DS27 mode preference; ties use nomination confidence, then unique count.
    return min(valid,key=lambda r:(ORDER.index(r['mode']),-r['identity']['minimum_margin'],
        -r['qualification']['added_points']['fitted_c'],r['track_id'])) if valid else None

def prepare():
    if (STUDY/'protocol.json').exists():return read(STUDY/'protocol.json')
    sys.path.insert(0,str(BASE))
    import report_dataset
    from report_dataset import published_owners
    freeze=read(BASE/'source-freeze.json');repo=Path('/srv/bulk/leo-dev/fast-algo02-production-v1')
    original_check=report_dataset.check_hash;archived=[]
    def check_historical_source(path,expected):
        path=Path(path)
        if path.is_relative_to(repo) and freeze['files_sha256'].get(str(path))==expected and digest(path)!=expected:
            data=subprocess.check_output(['git','show',freeze['source_commit']+':'+str(path.relative_to(repo))],cwd=repo)
            if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('archived source hash mismatch: '+str(path))
            archived.append(dict(path=str(path),commit=freeze['source_commit'],sha256=expected))
        else:original_check(path,expected)
    report_dataset.check_hash=check_historical_source
    try:_,members=report_dataset.verify_study(BASE)
    finally:report_dataset.check_hash=original_check
    write(STUDY/'historical-source-verification.json',dict(verified=True,archived_git_sources=archived,
        all_data_and_outcome_hashes_checked_at_original_paths=True))
    roster=[];jobs=[];excluded=[]
    for member,receipt,outcome in members:
        case=member['case'];root=BASE/'cases'/case
        if outcome is None:
            roster.append(dict(case=case,state=receipt['state'],reason=receipt.get('reason')));continue
        old=read(outcome['baseline_terminal'])
        arms=outcome['selected']['arms'] if outcome.get('selected') else outcome['baseline']['arms']
        owners={a:(arms[a]['owners'] if 'owners' in arms[a] else published_owners(old,a)) for a in ('c0','fitted_c')}
        inv_path=next((root/'all-large-track-recovery').glob('*/inventory.json'));inv=read(inv_path)
        obs_path=Path(inv['job']['root'])/inv['job']['case']/'observations.json'
        universe={o['observation_id'] for o in read(obs_path)}
        if any(not set(v)<=universe for v in owners.values()):raise ValueError('baseline IDs outside public input')
        write(STUDY/'baselines'/f'{case}.json',dict(case=case,arms=arms,owners=owners,observation_ids=sorted(universe),
            source=str(root/'outcome.json'),source_sha256=digest(root/'outcome.json'),
            historical_read_audit_verified=bool((old.get('read_audit') or {}).get('verified'))))
        roster.append(dict(case=case,state='complete',glrt_points=len(universe),
            baseline_path=str(STUDY/'baselines'/f'{case}.json'),baseline_sha256=digest(STUDY/'baselines'/f'{case}.json')))
        decision=read(root/'decision.json')
        for attempt in decision['attempts']:
            if not attempt.get('shared_family') or attempt['status']!='RF_rejected':continue
            tid=attempt['track_id'];validation=root/tid/'annotation';r=read(validation/'result.json')
            identity=r['annotation'];pr=read(validation/'protocol.json')
            reason=None
            if identity['status']!='conditionally_supported_identity':reason='identity_not_supported'
            elif r.get('graph_bundle') or r.get('inactive_graph_fragment') or pr['target'].get('native_branch_source'):reason='non_full_parent_source'
            elif set(pr['target']['observation_ids']) & (set(owners['c0'])|set(owners['fitted_c'])):reason='already_owned_or_partially_owned_by_ALGO04'
            if reason:
                excluded.append(dict(case=case,track_id=tid,reason=reason));continue
            jobs.append(dict(case=case,track_id=tid,inventory=str(inv_path),validation=str(validation),recovery=str(root),
                key=r['component'],points=attempt['points'],identity=identity,
                baseline_path=str(STUDY/'baselines'/f'{case}.json'),
                source_sha256={str(p):digest(p) for p in (inv_path,validation/'result.json',validation/'protocol.json')}))
    protocol=dict(roster=roster,targets=jobs,excluded=excluded,workers=12,modes=list(MODES),
        gap_modes=['gap_default','gap_conditional'],mode_preference=list(ORDER),
        tie_break='strongest minimum nomination margin, then added points, then stable target ID',
        no_union_of_independent_trials=True,no_GPS_inference=True,causal_only=True,
        maximum_full_fit_seconds=360,maximum_gap_fit_seconds=240,maximum_annotation_seconds=240,maximum_audit_seconds=180,
        gap_s=5,minimum_fragment_points=12,minimum_fragment_span_s=10,
        both_c_arms=True,production_changed=False,baseline_is_sealed_ALGO04_equivalent_replay=True,
        source_sha256={str(p):digest(p) for p in (Path(__file__),PRIOR/'qualification.py',PRIOR/'gap_stage.py',
            BASE/'final-dataset-seal.json',BASE/'dataset-protocol.json',RELEASE/'release-manifest.json')})
    write(STUDY/'protocol.json',protocol)
    print('Prepared',len(roster),'fast scans;',len(jobs),'targets;',len(excluded),'excluded',flush=True)
    return protocol

def stage(command,log,timeout):
    receipt=log.with_suffix('.receipt.json')
    if receipt.exists():return read(receipt)
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
        PYTHONPATH=f'{RELEASE}/src:{RELEASE}/tools',MPLCONFIGDIR=str(STUDY/'mpl-cache'))
    log.parent.mkdir(parents=True,exist_ok=True);began=time.monotonic()
    with log.open('x') as stream:
        process=subprocess.Popen(list(map(str,command)),stdout=stream,stderr=subprocess.STDOUT,
            env=env,cwd=RELEASE,start_new_session=True)
        try:
            code=process.wait(timeout=timeout);state='complete' if code==0 else 'failed'
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);code=process.wait();state='timeout'
    result=dict(state=state,returncode=code,seconds=time.monotonic()-began,timeout_s=timeout,command=list(map(str,command)))
    write(receipt,result);return result

def audit_and_qualify(t,out,mode,fit,identity):
    audit=None
    if fit['state']=='complete':
        wrapper=STUDY/'gap_wrapper.py' if mode.startswith('gap_') else RELEASE/'tools/algo04_numerical_stage.py'
        prefix=[sys.executable,str(wrapper)]
        if not mode.startswith('gap_'):
            prefix+=['--reference-limit-s','30','--centered-lbfgsb','--receipt',str(out.parent/(out.name+'-audit-numerics.json'))]
        script='audit_shared_predictive_inclusion.py'
        cmd=prefix+[script if mode.startswith('gap_') else str(RELEASE/'tools'/script),
            '--study',t['recovery'],'--trial',str(out),'--output',str(out/'exact_owner_replay.json')]
        audit=stage(cmd,out.parent/(out.name+'-audit.log'),180)
    if fit['state']=='complete':
        proof=read(out/'exact_owner_replay.json') if audit and audit['state']=='complete' else None
        baseline=read(t['baseline_path']);q=qualify(read(out/'target_0.json'),proof,baseline['owners'],set(baseline['observation_ids']))
        if not baseline['historical_read_audit_verified']:
            q['qualified']=False;q['reasons'].append('historical ALGO03 read audit not verified')
    else:q=dict(qualified=False,reasons=['stage '+fit['state']],added_points={a:0 for a in ('c0','fitted_c')})
    return dict(case=t['case'],track_id=t['track_id'],mode=mode,path=str(out),fit=fit,audit=audit,
        identity=identity,qualification=q)

def work(t):
    root=STUDY/'targets'/t['case']/t['track_id'];root.mkdir(parents=True,exist_ok=True)
    result_path=root/'result.json'
    if result_path.exists():return read(result_path)
    rows=[]
    for mode in MODES:
        out=root/mode
        flags={'marginal':['--shared-satellite-refresh'],'conditional':['--conditional-satellite-refresh'],
            'conditional_feasible':['--conditional-satellite-refresh','--position-fit','incumbent_feasible']}[mode]
        cmd=[sys.executable,str(RELEASE/'tools/algo04_numerical_stage.py'),
            '--reference-limit-s','30','--centered-lbfgsb','--receipt',str(root/(mode+'-numerics.json')),
            str(RELEASE/'tools/include_predictive_annotations.py'),'--inventory',t['inventory'],
            '--validation',t['validation'],'--output',str(out),'--predictive-member',*flags]
        fit=stage(cmd,root/(mode+'.log'),360)
        rows.append(audit_and_qualify(t,out,mode,fit,t['identity']))
        write(root/'partial.json',rows)
    source=root/'gap-source/branches.json'
    prep=stage([sys.executable,str(STUDY/'gap_wrapper.py'),'prepare',str(root),json.dumps(t)],root/'gap-prepare.log',180)
    gap_annotations=[]
    if prep['state']=='complete':
        for branch in read(source)['branches']:
            # A full unchanged parent is already tested; do not rename it a new fragment.
            if len(branch['observation_ids'])==t['points']:continue
            gap_root=root/('gap-'+branch['branch_id']);validation=gap_root/'annotation'
            cmd=[sys.executable,str(STUDY/'gap_wrapper.py'),'annotate_predictive_only.py','--inventory',t['inventory'],
                '--output',str(validation),'--track',branch['branch_id'],'--native-branches',str(source),
                '--distinct-partitions','--candidates','3','--folds','3','--uncalibrated-phase-mixture']
            annotation=stage(cmd,gap_root/'annotation.log',240)
            rec=dict(branch_id=branch['branch_id'],points=len(branch['observation_ids']),execution=annotation)
            if annotation['state']=='complete':
                identity=read(validation/'result.json')['annotation'];rec['identity']=identity
                if identity['status']=='conditionally_supported_identity':
                    for mode,flags in [('gap_default',[]),('gap_conditional',['--conditional-satellite-refresh'])]:
                        out=gap_root/mode
                        cmd=[sys.executable,str(STUDY/'gap_wrapper.py'),'include_predictive_annotations.py',
                            '--inventory',t['inventory'],'--validation',str(validation),'--output',str(out),
                            '--native-from-validation',*flags]
                        fit=stage(cmd,gap_root/(mode+'.log'),240)
                        rows.append(audit_and_qualify(t,out,mode,fit,identity))
            gap_annotations.append(rec)
            write(root/'partial.json',rows)
    for p,h in t['source_sha256'].items():
        if digest(p)!=h:raise ValueError('immutable source changed')
    result=dict(case=t['case'],track_id=t['track_id'],trials=rows,gap_preparation=prep,gap_annotations=gap_annotations)
    write(result_path,result)
    print(t['case'],t['track_id'],'complete',len(rows),'trials',sum(r['qualification']['qualified'] for r in rows),'qualified',flush=True)
    return result

def run():
    protocol=prepare();results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures={pool.submit(work,t):t for t in protocol['targets']}
        for future in concurrent.futures.as_completed(futures):
            t=futures[future]
            try:result=future.result()
            except Exception as e:
                result=dict(case=t['case'],track_id=t['track_id'],trials=[],failure=type(e).__name__+': '+str(e))
            results.append(result)
            write(STUDY/'progress.json',dict(completed=len(results),total=len(futures),results=results))
    selections=[]
    for case in protocol['roster']:
        trials=[r for z in results if z['case']==case['case'] for r in z['trials']]
        selections.append(dict(case=case['case'],state=case['state'],selected=selected_trial(trials)))
    write(STUDY/'execution.json',results);write(STUDY/'selections.json',selections)
    write(STUDY/'inference-seal.json',dict(no_GPS_inference=True,files={str(p):digest(p) for p in
        [STUDY/'protocol.json',STUDY/'execution.json',STUDY/'selections.json',*sorted((STUDY/'baselines').glob('*.json')),
         *sorted((STUDY/'targets').rglob('target_0.json')),*sorted((STUDY/'targets').rglob('control.json')),
         *sorted((STUDY/'targets').rglob('exact_owner_replay.json'))]}))

if __name__=='__main__':
    prepare() if len(sys.argv)>1 and sys.argv[1]=='prepare' else run()
