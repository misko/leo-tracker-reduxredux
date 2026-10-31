"""Seal RF decisions before introducing geographic truth for evaluation."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_trials import STUDY, SOURCE, read, write, targets
from qualification import qualify, ARMS
sys.path.insert(0,str(SOURCE))
from rank_native_residuals import published_owners
from report_ds27 import chosen_arms,distance

DEST=Path('/srv/bulk/leo-dev/fast-algo02-production-v1/reports/2026_10_31_ds27_confident_recovery')
ORDER=['conditional','gap_default','gap_conditional','conditional_feasible','marginal']

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def seal():
    # Require complete bounded scheduling receipts; unavailable stages remain failures.
    for name in ('execution.json','conditional_feasible-execution.json','gap-execution.json'):
        if not (STUDY/name).exists():raise ValueError('unfinished scheduling: '+name)
    index={r['case']:r for r in read(SOURCE/'analysis-index.json')['cases']}
    decisions=[]
    for t in targets():
        for p,h in t['source_hashes'].items():
            if sha(p)!=h:raise ValueError('frozen source changed')
        terminal=read(index[t['case']]['terminal_path'])
        owners={a:published_owners(terminal,a) for a in ARMS}
        universe={o['observation_id'] for o in read(index[t['case']]['observations_path'])}
        trials=[]
        for path in sorted((STUDY/t['case']).rglob('target_0.json')):
            value=read(path);audit_path=path.parent/'exact_owner_replay.json'
            audit=read(audit_path) if audit_path.exists() else None
            validation=read(path.parent/'protocol.json')['annotation_receipts'][0]['path']
            identity=read(Path(validation)/'result.json')['annotation']
            q=qualify(value,audit,owners,universe)
            if identity['status']!='conditionally_supported_identity':
                q['qualified']=False;q['reasons'].append('identity not supported')
            trials.append(dict(case=t['case'],mode=path.parent.name,path=str(path),
                audit_path=str(audit_path) if audit else None,identity=identity,**q))
        eligible=[r for r in trials if r['qualified']]
        selected=min(eligible,key=lambda r:ORDER.index(r['mode'])) if eligible else None
        decisions.append(dict(case=t['case'],trials=trials,selected=selected,
            baseline_terminal=index[t['case']]['terminal_path'],glrt_points=len(universe)))
    all_files=[p for p in STUDY.rglob('*') if p.is_file() and p.suffix in ('.json','.py')
               and p.name not in ('inference-seal.json','rf-decisions.json') and '__pycache__' not in p.parts]
    write(STUDY/'rf-decisions.json',dict(decisions=decisions,selection_order=ORDER,
        no_GPS_in_selection=True,research_only=True,production_changed=False))
    write(STUDY/'inference-seal.json',dict(files={str(p):sha(p) for p in all_files},
        decisions_sha256=sha(STUDY/'rf-decisions.json'),truth_not_loaded=True))
    return decisions

def report():
    decisions=seal()
    # Evaluation site is introduced only after the inference/decision hash seal.
    truth=(37.849061591561885,-122.48574968092912)
    DEST.mkdir(exist_ok=False,parents=True);(DEST/'figures').mkdir();(DEST/'evidence').mkdir();(DEST/'reproduction').mkdir()
    rows=[];paired=[];failed=[]
    for case in decisions:
        terminal=read(case['baseline_terminal']);baseline=chosen_arms(terminal)
        owners={a:published_owners(terminal,a) for a in ARMS}
        selected=read(case['selected']['path']) if case['selected'] else None
        for arm in ARMS:
            b=baseline[arm];r=selected['arms'][arm] if selected else b
            associated=len(r['proposed_associated_ids']) if selected else len(owners[arm])
            paired.append(dict(case=case['case'],arm=arm,mode=case['selected']['mode'] if selected else 'ALGO04 fallback',
                baseline_associated=len(owners[arm]),associated=associated,glrt_points=case['glrt_points'],
                baseline_percent=100*len(owners[arm])/case['glrt_points'],percent=100*associated/case['glrt_points'],
                baseline_error_m=1000*distance(b['endpoint_latlon'],truth),error_m=1000*distance(r['endpoint_latlon'],truth)))
        for trial in case['trials']:
            result=read(trial['path']);control=read(Path(trial['path']).parent/'control.json')
            audit=read(trial['audit_path']) if trial['audit_path'] else None
            for arm,r in result['arms'].items():
                ar=next((v for v in audit['rows'] if v['role']=='target_0' and v['arm']==arm),None) if audit else None
                slacks={k:v for e in ar['exact_family_replays'] for k,v in e['all_gate_slacks'].items()} if ar else {}
                failures={k:v for k,v in slacks.items() if v<0}
                diag=r['target_diagnostics'][0]
                rows.append(dict(case=case['case'],mode=trial['mode'],arm=arm,qualified=trial['qualified'],
                    reason='; '.join(trial['reasons']),target_points=len(diag['times_s']),
                    proposed_points=len(r['proposed_associated_ids']),accepted_additions=trial['added_points'][arm] if trial['qualified'] else 0,
                    trial_error_m=1000*distance(r['endpoint_latlon'],truth),control_error_m=1000*distance(control['arms'][arm]['endpoint_latlon'],truth),
                    target_RMS_hz=diag['RMS_hz'],target_bias_hz=diag['bias_hz'],
                    minimum_gate_slack=min(slacks.values()) if slacks else None,
                    changed_old_owners=len(ar['incumbent_ownership_changes']) if ar else None,
                    final_phase_change_s=r['final_phase_change_s'],frequency_objective=r['negative_twice_elbo'],
                    conditional_old_RMS_hz=r['RMS_hz']))
                failed.extend(dict(case=case['case'],mode=trial['mode'],arm=arm,gate=k,slack=v) for k,v in failures.items())
    def csvwrite(name,rr):
        with (DEST/name).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rr[0]),lineterminator='\n');w.writeheader();w.writerows(rr)
    csvwrite('all-trials.csv',rows);csvwrite('accepted-policy.csv',paired);csvwrite('failed-gates.csv',failed)
    baseline_rows=list(csv.DictReader((SOURCE/'results/per-case.csv').open()))
    totals={}
    for arm in ARMS:
        base=[r for r in baseline_rows if r['method']=='ALGO04' and r['arm']==arm and r['state']=='complete']
        updates={r['case']:r for r in paired if r['arm']==arm}
        old=[float(r['error_km'])*1000 for r in base]
        new=[updates[r['case']]['error_m'] if r['case'] in updates else float(r['error_km'])*1000 for r in base]
        count=sum(int(r['associated']) for r in base)
        added=sum(r['associated']-r['baseline_associated'] for r in updates.values())
        denom=sum(int(r['glrt_points']) for r in base)
        totals[arm]=dict(usable_scans=len(base),original_points=count,new_points=count+added,added=added,
            denominator=denom,original_percent=100*count/denom,new_percent=100*(count+added)/denom,
            original_mean_error_m=float(np.mean(old)),new_mean_error_m=float(np.mean(new)),
            original_median_error_m=float(np.median(old)),new_median_error_m=float(np.median(new)),
            original_within500=sum(e<=500 for e in old),new_within500=sum(e<=500 for e in new))
    write(DEST/'summary.json',dict(totals=totals,selected=paired,qualified_trials=sum(t['qualified'] for d in decisions for t in d['trials']),
        total_trials=sum(len(d['trials']) for d in decisions),production_changed=False,
        generalization='Selected difficult cases only; remaining DS27 scans retain frozen ALGO04 results'))
    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for col,arm in enumerate(ARMS):
        rr=[r for r in paired if r['arm']==arm];x=np.arange(len(rr))
        for k,key,label,color in [(0,'baseline_','ALGO04','#888888'),(1,'','Qualified research policy','#0072b2')]:
            axs[0,col].bar(x+(k-.5)*.34,[r[key+'percent'] for r in rr],.34,label=label,color=color)
            axs[1,col].bar(x+(k-.5)*.34,[r[key+'error_m'] for r in rr],.34,label=label,color=color)
        for ax in axs[:,col]:ax.set_xticks(x,[r['case'].replace('DS27-','') for r in rr]);ax.grid(axis='y',alpha=.2)
        axs[0,col].set(title=arm,ylabel='GLRT associated (%)',ylim=(0,100));axs[0,col].legend(fontsize=8)
        axs[1,col].set(ylabel='Position error (m)',xlabel='DS27 scan');axs[1,col].axhline(500,color='k',ls=':',lw=1)
    fig.suptitle('Qualified recovery versus ALGO04 — all rejected trials fall back\nKnown site used only for error reporting; research results, no production change')
    fig.savefig(DEST/'figures/coverage-and-position.png',dpi=160);plt.close(fig)
    fig,axs=plt.subplots(4,1,figsize=(12,12),layout='constrained')
    for ax,case in zip(axs,decisions,strict=True):
        t=next(t for t in targets() if t['case']==case['case']);base=read(Path(t['recovery'])/t['track_id']/'trial/target_0.json')
        d=base['arms']['fitted_c']['target_diagnostics'][0]
        ax.plot(d['times_s'],d['residual_hz'],'.-',color='gray',label='ALGO04 rejected trial')
        for mode,color in [('conditional','#e69f00'),('conditional_feasible','#cc79a7'),('gap_default','#009e73')]:
            tr=next((r for r in case['trials'] if r['mode']==mode),None)
            if tr:
                d=read(tr['path'])['arms']['fitted_c']['target_diagnostics'][0]
                ax.plot(d['times_s'],d['residual_hz'],'.-',ms=3,color=color,label=mode+(' — qualified' if tr['qualified'] else ' — rejected'))
        ax.axhline(0,color='k',lw=.6);ax.set(title=case['case']+' '+t['key'].split('-RF')[0],ylabel='Profile residual (Hz)',xlabel='Time (s)')
        ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=2)
    fig.savefig(DEST/'figures/residual-comparison.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5),layout='constrained');x=np.arange(len(decisions))
    for k,relation,label in [(0,None,'Unassociated target'),(1,'same_satellite_other_curve','Other curves, same satellite'),(2,'same_receiver','Other satellites, same receiver')]:
        values=[]
        for d in decisions:
            v=next(r for r in read(STUDY/d['case']/'control-witnesses.json')['results'] if r['arm']=='fitted_c')
            values.append(v['target_rate']['slope_hz_s'] if relation is None else next(g['predicted_target_rate_hz_s'] for g in v['groups'] if g['group']==relation and g['scaling']=='hz'))
        ax.bar(x+(k-1)*.25,values,.25,label=label)
    ax.set_xticks(x,[d['case'] for d in decisions]);ax.axhline(0,color='k',lw=.6);ax.set(ylabel='Descriptive residual slope (Hz/s)',title='Full-fit witnesses: large target slopes are not shared across the family')
    ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2);fig.savefig(DEST/'figures/witness-slopes.png',dpi=150);plt.close(fig)
    evidence_map={}
    for p in sorted(STUDY.rglob('*')):
        if not p.is_file() or p.suffix not in ('.json','.py','.log') or '__pycache__' in p.parts:continue
        rel=p.relative_to(STUDY)
        dest=DEST/('reproduction' if p.suffix=='.py' else 'evidence')/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        data=p.read_bytes()
        if p.suffix=='.json' and len(data)>100000:
            dest=dest.with_suffix('.json.gz');dest.write_bytes(gzip.compress(data,mtime=0))
        else:dest.write_bytes(data)
        evidence_map[str(dest.relative_to(DEST))]=dict(source=str(p),source_sha256=sha(p),published_sha256=sha(dest))
    write(DEST/'artifact-map.json',evidence_map)
    print(json.dumps(totals,indent=2))

if __name__=='__main__':report()
