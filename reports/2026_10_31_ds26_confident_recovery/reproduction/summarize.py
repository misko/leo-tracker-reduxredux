"""Evaluate sealed DS26 recovery fits; truth is reporting-only."""
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
import shutil
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from evaluate import STUDY,BASE,PRIOR,MODES,ORDER,read,write,digest,selected_trial

OUT=Path('/srv/bulk/leo-dev/fast-algo02-production-v1/reports/2026_10_31_ds26_confident_recovery')

def distance(position,truth):
    lat,lon,tlat,tlon=map(math.radians,(*position,*truth))
    a=math.sin((lat-tlat)/2)**2+math.cos(lat)*math.cos(tlat)*math.sin((lon-tlon)/2)**2
    return 12742017.6*math.atan2(math.sqrt(a),math.sqrt(max(0,1-a)))

def method_trial(trials,mode):
    rows=[r for r in trials if r['qualification']['qualified'] and (mode=='combined_policy' or r['mode']==mode)]
    return selected_trial(rows)

def summarize_values(rows):
    valid=[r for r in rows if r['state']=='complete']
    errors=np.array([r['error_m'] for r in valid]);old=np.array([r['baseline_error_m'] for r in valid])
    total=sum(r['glrt_points'] for r in valid);associated=sum(r['associated'] for r in valid)
    return dict(usable=len(valid),unavailable=len(rows)-len(valid),associated=associated,total_GLRT=total,
        associated_percent=100*associated/total,added_points=sum(r['added_points'] for r in valid),
        changed_scans=sum(r['added_points']>0 for r in valid),mean_error_m=float(errors.mean()),
        median_error_m=float(np.median(errors)),p95_error_m=float(np.quantile(errors,.95)),worst_error_m=float(errors.max()),
        within500=int(sum(errors<=500)),improved_over_1m=int(sum(errors-old < -1)),worse_over_1m=int(sum(errors-old > 1)),
        mean_change_m=float(np.mean(errors-old)))

def csvwrite(path,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w') as stream:
        w=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)

def report():
    seal=read(STUDY/'inference-seal.json')
    assert seal['no_GPS_inference']
    for path,h in seal['files'].items():
        if digest(path)!=h:raise ValueError('changed inference artifact: '+path)
    for path,h in read(STUDY/'additional-source-receipt.json')['sha256'].items():
        if digest(path)!=h:raise ValueError('changed supplementary source: '+path)
    protocol=read(STUDY/'protocol.json');execution=read(STUDY/'execution.json');selection=read(STUDY/'selections.json')
    if len(execution)!=len(protocol['targets']):raise ValueError('unfinished target roster')
    expected={(t['case'],t['track_id']) for t in protocol['targets']}
    if {(r['case'],r['track_id']) for r in execution}!=expected:raise ValueError('target coverage differs')
    bycase={c['case']:[t for r in execution if r['case']==c['case'] for t in r['trials']] for c in protocol['roster']}
    for r in selection:
        if r['selected']!=selected_trial(bycase[r['case']]):raise ValueError('selection changed')
    # No selection or qualification uses the following evaluation coordinates.
    truth=(37.849061591561885,-122.48574968092912)
    OUT.mkdir(parents=True,exist_ok=False);(OUT/'figures').mkdir();(OUT/'evidence').mkdir();(OUT/'reproduction').mkdir()
    methods=['ALGO04',*MODES,'gap_default','gap_conditional','combined_policy'];rows=[];trials=[];failures=[];compact=[]
    for c in protocol['roster']:
        if c['state']!='complete':
            rows.extend(dict(case=c['case'],method=m,arm=a,state=c['state'],reason=c.get('reason')) for m in methods for a in ('c0','fitted_c'))
            continue
        b=read(c['baseline_path']);total=len(b['observation_ids'])
        for m in methods:
            t=method_trial(bycase[c['case']],m) if m!='ALGO04' else None
            fit=read(Path(t['path'])/'target_0.json') if t else None
            control=read(Path(t['path'])/'control.json') if t else None
            for arm in ('c0','fitted_c'):
                old=b['arms'][arm];r=fit['arms'][arm] if fit else old
                count=len(r['proposed_owners']) if fit else len(b['owners'][arm])
                direct=set(o for e in fit['target_entries'] for o in e['observation_ids']) if fit else set()
                direct_added=len(direct & (set(r['proposed_owners'])-set(b['owners'][arm]))) if fit else 0
                rows.append(dict(case=c['case'],method=m,arm=arm,state='complete',selected_mode=t['mode'] if t else None,
                    track_id=t['track_id'] if t else None,trial_path=t['path'] if t else None,glrt_points=total,
                    baseline_associated=len(b['owners'][arm]),associated=count,added_points=count-len(b['owners'][arm]),
                    associated_percent=100*count/total,baseline_error_m=distance(old['endpoint_latlon'],truth),
                    error_m=distance(r['endpoint_latlon'],truth),
                    control_error_m=distance(control['arms'][arm]['endpoint_latlon'],truth) if control else None,
                    control_associated=len(control['arms'][arm]['proposed_owners']) if control else None,
                    control_preserves_baseline=all(control['arms'][arm]['proposed_owners'].get(i)==n for i,n in b['owners'][arm].items()) if control else None,
                    direct_target_added_points=direct_added,other_added_points=count-len(b['owners'][arm])-direct_added,
                    target_RMS_hz=r['target_diagnostics'][0]['RMS_hz'] if fit else None,
                    frequency_objective=r.get('negative_twice_elbo')))
        for t in bycase[c['case']]:
            p=Path(t['path']);fit=read(p/'target_0.json') if (p/'target_0.json').exists() else None
            control=read(p/'control.json') if (p/'control.json').exists() else None
            audit=read(p/'exact_owner_replay.json') if (p/'exact_owner_replay.json').exists() else None
            compact_trial=dict(case=c['case'],track_id=t['track_id'],mode=t['mode'],trial_path=t['path'],qualification=t['qualification'],identity=t['identity'],
                source_hashes={str(f):digest(f) for f in (p/'target_0.json',p/'control.json',p/'exact_owner_replay.json') if f.exists()},arms={})
            for arm in ('c0','fitted_c'):
                r=fit['arms'][arm] if fit else None
                a=next((a for a in audit['rows'] if a['role']=='target_0' and a['arm']==arm),None) if audit else None
                slacks={k:v for e in a['exact_family_replays'] for k,v in e['all_gate_slacks'].items()} if a else {}
                bad={k:v for k,v in slacks.items() if v<0}
                oldowners=b['owners'][arm]
                controlowners=control['arms'][arm]['proposed_owners'] if control else None
                owners=r['proposed_owners'] if r else None
                trials.append(dict(case=c['case'],track_id=t['track_id'],mode=t['mode'],arm=arm,trial_path=t['path'],
                    qualified=t['qualification']['qualified'],reason='; '.join(t['qualification']['reasons']),fit_state=t['fit']['state'],
                    target_points=len(r['target_diagnostics'][0]['times_s']) if r else None,
                    trial_error_m=distance(r['endpoint_latlon'],truth) if r else None,
                    control_error_m=distance(control['arms'][arm]['endpoint_latlon'],truth) if control else None,
                    target_RMS_hz=r['target_diagnostics'][0]['RMS_hz'] if r else None,
                    minimum_gate_slack=min(slacks.values()) if slacks else None,
                    owner_changes=len(a['incumbent_ownership_changes']) if a else None,
                    control_paired_valid=control['paired_valid'] if control else None,
                    control_baseline_missing=sum(i not in controlowners for i in oldowners) if controlowners is not None else None,
                    control_baseline_reassigned=sum(i in controlowners and controlowners[i]!=n for i,n in oldowners.items()) if controlowners is not None else None,
                    trial_baseline_missing=sum(i not in owners for i in oldowners) if owners is not None else None,
                    trial_baseline_reassigned=sum(i in owners and owners[i]!=n for i,n in oldowners.items()) if owners is not None else None,
                    trial_control_missing=sum(i not in owners for i in controlowners) if owners is not None and controlowners is not None else None,
                    added_points=t['qualification'].get('added_points',{}).get(arm,0) if t['qualification']['qualified'] else 0,
                    frequency_objective=r.get('negative_twice_elbo') if r else None,
                    final_phase_change_s=r['final_phase_change_s'] if r else None))
                target_components={d['component'] for d in r['target_diagnostics']} if r else set()
                failures.extend(dict(case=c['case'],track_id=t['track_id'],mode=t['mode'],arm=arm,trial_path=t['path'],
                    scope='target' if any(k.startswith(component+'/') for component in target_components) else 'existing',
                    gate=k,slack=v) for k,v in bad.items())
                if r:
                    compact_trial['arms'][arm]=dict(endpoint_latlon=r['endpoint_latlon'],endpoint_east_north_km=r['endpoint_east_north_km'],
                        frequency_objective=r['negative_twice_elbo'],target_diagnostics=r['target_diagnostics'],
                        control_endpoint=control['arms'][arm]['endpoint_latlon'] if control else None,
                        exact_gate_slacks=slacks,owner_changes=a['incumbent_ownership_changes'] if a else None,
                        phase_reference_check=a['phase_reference_check'] if a else None,
                        source_owners_sha256=hashlib.sha256(json.dumps(r['proposed_owners'],sort_keys=True).encode()).hexdigest(),
                        new_owners={i:n for i,n in r['proposed_owners'].items() if i not in b['owners'][arm]})
            compact.append(compact_trial)
    csvwrite(OUT/'per-case.csv',rows);csvwrite(OUT/'all-trials.csv',trials);csvwrite(OUT/'failed-gates.csv',failures)
    changed=[r for r in rows if r['method']=='combined_policy' and r['state']=='complete' and r['added_points']>0]
    csvwrite(OUT/'changed-scans.csv',changed)
    metrics={m:{a:summarize_values([r for r in rows if r['method']==m and r['arm']==a]) for a in ('c0','fitted_c')} for m in methods}
    stagecounts={}
    for p in (STUDY/'targets').rglob('*.receipt.json'):
        state=read(p)['state'];stagecounts[state]=stagecounts.get(state,0)+1
    paired=[t for r in execution for t in r['trials']]
    mode_counts={m:dict(attempted=sum(t['mode']==m for t in paired),
        qualified=sum(t['mode']==m and t['qualification']['qualified'] for t in paired),
        selected_scans=metrics[m]['fitted_c']['changed_scans'],
        rejection_reasons=dict(Counter(reason for t in paired if t['mode']==m for reason in t['qualification']['reasons'])))
        for m in methods if m not in ('ALGO04','combined_policy')}
    summary=dict(metrics=metrics,mode_counts=mode_counts,target_roster=len(protocol['targets']),target_cases=len({t['case'] for t in protocol['targets']}),
        paired_trials=len(trials)//2,qualified_paired_trials=sum(t['qualified'] for t in trials)//2,
        gap_annotations=sum(len(r.get('gap_annotations',[])) for r in execution),
        gap_annotation_states=dict(Counter(a.get('identity',{}).get('status',a['execution']['state']) for r in execution for a in r.get('gap_annotations',[]))),
        unavailable_states=dict(Counter(r['state'] for r in protocol['roster'] if r['state']!='complete')),
        excluded_candidates=protocol['excluded'],
        target_failures=[{k:v for k,v in r.items() if k!='trials'} for r in execution if r.get('failure')],
        control_does_not_preserve_baseline_cases=sorted({r['case'] for r in trials if (r['control_baseline_missing'] or 0)+(r['control_baseline_reassigned'] or 0)>0}),
        stage_counts=stagecounts,production_changed=False)
    write(OUT/'summary.json',summary)
    (OUT/'evidence/trial-diagnostics.json.gz').write_bytes(gzip.compress(json.dumps(compact,separators=(',',':'),allow_nan=False).encode(),mtime=0))
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    colors={'ALGO04':'black','marginal':'#999999','conditional':'#e69f00','conditional_feasible':'#cc79a7',
        'gap_default':'#009e73','gap_conditional':'#56b4e9','combined_policy':'#0072b2'}
    for ax,arm in zip(axs,('c0','fitted_c')):
        for m in methods:
            e=sorted(r['error_m']/1000 for r in rows if r['method']==m and r['arm']==arm and r['state']=='complete')
            ax.step(e,np.arange(1,len(e)+1)/len(e),where='post',color=colors[m],label=m,lw=2 if m in ('ALGO04','combined_policy') else 1,alpha=.9)
        ax.axvline(.5,color='k',ls=':',lw=.7);ax.set(xlabel='Position error (km)',ylabel='Fraction of 148 usable scans',title=arm);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('DS26: frozen ALGO04 versus DS27 recovery variants\nAll failed, ineligible and unsupported additions retain the incumbent')
    fig.savefig(OUT/'figures/error-cdf.png',dpi=160);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,6),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c')):
        rr=[r for r in rows if r['method']=='combined_policy' and r['arm']==arm and r['state']=='complete']
        limit=max(max(r['baseline_error_m'],r['error_m']) for r in rr)/1000*1.05
        ax.plot([0,limit],[0,limit],color='gray',ls='--')
        ax.scatter([r['baseline_error_m']/1000 for r in rr],[r['error_m']/1000 for r in rr],c=[r['added_points'] for r in rr],cmap='viridis',s=28)
        for r in rr:
            if r['added_points']>0 and abs(r['error_m']-r['baseline_error_m'])>100:
                ax.annotate(r['case'].replace('DS26-',''),(r['baseline_error_m']/1000,r['error_m']/1000),fontsize=7)
        ax.set(xlabel='ALGO04 error (km)',ylabel='Recovery policy error (km)',title=arm,xlim=(0,limit),ylim=(0,limit));ax.grid(alpha=.2)
    fig.suptitle('Points above the diagonal are worse; colors encode recovered count')
    fig.savefig(OUT/'figures/paired-errors.png',dpi=160);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c')):
        rr=[r for r in changed if r['arm']==arm]
        ax.scatter([r['added_points'] for r in rr],[(r['error_m']-r['baseline_error_m']) for r in rr],color='#0072b2')
        for r in rr:ax.annotate(r['case'].replace('DS26-',''),(r['added_points'],r['error_m']-r['baseline_error_m']),fontsize=7)
        ax.axhline(0,color='gray',ls='--');ax.set(xlabel='Additional unique GLRT observations',ylabel='Position error change (m)',title=arm);ax.grid(alpha=.2)
    fig.suptitle('Coverage gain versus localization change: negative is improvement')
    fig.savefig(OUT/'figures/coverage-versus-error.png',dpi=160);plt.close(fig)
    variants=methods[1:];y=np.arange(len(variants))
    fig,axs=plt.subplots(1,2,figsize=(12,6),layout='constrained')
    gain=[metrics[m]['fitted_c']['associated_percent']-metrics['ALGO04']['fitted_c']['associated_percent'] for m in variants]
    bars=axs[0].barh(y,gain,color='#009e73');axs[0].bar_label(bars,labels=[f"+{metrics[m]['fitted_c']['added_points']} points" for m in variants],padding=4,fontsize=8)
    axs[0].set(yticks=y,yticklabels=variants,xlabel='GLRT association gain (percentage points)',title='Unique native observations')
    axs[0].margins(x=.35)
    for offset,arm,color in [(-.18,'c0','#0072b2'),(.18,'fitted_c','#e69f00')]:
        bars=axs[1].barh(y+offset,[metrics[m][arm]['mean_change_m'] for m in variants],height=.33,label=arm,color=color)
        axs[1].bar_label(bars,fmt='%+.1f m',padding=4,fontsize=8)
    axs[1].axvline(0,color='black',lw=.7);axs[1].set(yticks=y,yticklabels=variants,xlabel='Mean position error change (m)',title='Negative is improvement; 148 usable scans')
    axs[1].margins(x=.25);axs[1].legend()
    for ax in axs:ax.invert_yaxis();ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('DS26: separate coverage gain from localization accuracy\nEach method retains ALGO04 when its recovery does not qualify')
    fig.savefig(OUT/'figures/method-summary.png',dpi=160);plt.close(fig)
    kinds=sorted({r['gate'].split('/')[-1] for r in failures})
    fig,ax=plt.subplots(figsize=(11,5),layout='constrained');y=np.arange(len(kinds))
    for offset,scope,color in [(-.18,'target','#d55e00'),(.18,'existing','#0072b2')]:
        counts=[len({r['trial_path'] for r in failures if r['scope']==scope and r['gate'].split('/')[-1]==kind}) for kind in kinds]
        bars=ax.barh(y+offset,counts,height=.33,label=scope,color=color);ax.bar_label(bars,padding=3,fontsize=8)
    ax.set(yticks=y,yticklabels=kinds,xlabel='Paired trials with at least one failure of this type',
        title='Exact replay failures: candidate versus existing evidence\nEither c arm; categories overlap; these counts do not establish causation')
    ax.invert_yaxis();ax.legend();ax.margins(x=.15);ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    fig.savefig(OUT/'figures/gate-failures.png',dpi=160);plt.close(fig)
    # Compact source receipts: full numerical files stay sealed locally rather than
    # duplicating gigabytes of repeated baseline IDs into the repository.
    mapping={}
    sources=[*STUDY.glob('*.py'),STUDY/'protocol.json',STUDY/'inference-seal.json',STUDY/'execution.json',STUDY/'selections.json',
        STUDY/'historical-source-verification.json',STUDY/'additional-source-receipt.json',STUDY/'test-receipt.json',
        STUDY/'installed-release-verification.json',
        PRIOR/'qualification.py',PRIOR/'gap_stage.py',PRIOR/'run_trials.py',
        PRIOR/'test_qualification.py',PRIOR/'test_gap_stage.py']
    for p in sources:
        target=OUT/('reproduction' if p.suffix=='.py' else 'evidence')/p.name;data=p.read_bytes()
        if len(data)>100000:target=target.with_suffix(target.suffix+'.gz');data=gzip.compress(data,mtime=0)
        target.write_bytes(data);mapping[str(target.relative_to(OUT))]=dict(source=str(p),source_sha256=digest(p),published_sha256=digest(target))
    write(OUT/'artifact-map.json',mapping)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':report()
