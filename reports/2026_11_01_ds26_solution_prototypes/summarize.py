"""Render the predeclared stress tests; select with RF scores, never site error."""
import csv, hashlib, json, math, subprocess
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prototype import OUT, PRIOR, INPUT, CASES, ARMS, SUSPECT, read, write, age_penalty

POLICIES=['none','linear24','quadratic24','grace48','hard48']
LABELS=['No penalty','24h half-life','Quadratic / 24h','48h grace','Hard 48h']

def dump_csv(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def best(trial,arm,qualified=True):
    rows=[r for r in trial['rows'] if r['arm']==arm and (r['qualified'] or not qualified)]
    return min(rows,key=lambda r:r['objective']) if rows else None

def main():
    data={};flat=[];meta={};age_rows=[];selected=[]
    for case in CASES:
        z=read(INPUT/(case+'.json'));before=z['baseline_owners'];base=read(PRIOR/case/'audit.json')['arms']
        original=read(Path(z['native_path'])/'nominal_elements.json');ledger=read(PRIOR/case/'tle-ledger.json')['causal']
        trials=[read(p) for p in sorted((OUT/case).glob('*-w*.json'))]
        old=SUSPECT[case];ages={};catalogue={}
        for n in sorted({t['new_norad'] for t in trials}|set(before['fitted_c'].values())):
            e=original.get(str(n));v=e['provenance'] if e else ledger[str(n)];lines=e['lines'] if e else ledger[str(n)]['lines']
            cutoff=z['scan_receipt']['cutoff_utc_ns'];epoch=v['element_epoch_utc_ns'];collected=v['collected_utc_ns']
            assert epoch<=cutoff and collected<=cutoff
            age=(cutoff-epoch)/3.6e12;ages[n]=age
            catalogue[n]=dict(age_h=age,epoch=epoch,collected=collected,element_sha256=hashlib.sha256('\n'.join(lines).encode()).hexdigest(),
                              matches_72h_ledger=lines==ledger[str(n)]['lines'] if str(n) in ledger else None)
        native=read(Path(z['native_path'])/'observations.json');denom=len({r['observation_id'] for r in native})
        data[case]=dict(trials=trials,base=base,ages=ages,owners=before,denom=denom)
        meta[case]=dict(catalogue=catalogue,denominator=denom,baseline_points={a:len(before[a]) for a in ARMS})
        for t in trials:
            for r in t['rows']:
                arm=r['arm'];unexpected=[o for o in r['reassigned_ids'] if (before[arm][o],r['proposed_owners'][o])!=(old,t['new_norad'])]
                assert not unexpected, 'unexpected incumbent reassignment'
                flat.append(dict(case=case,norad=t['new_norad'],age_h=ages[t['new_norad']],weight=t['weight'],constrained=t['constrained'],arm=arm,start=r['start'],
                    error_km=r['error_m']/1000,objective=r['objective'],rms_hz=r['rms_hz'],qualified=r['qualified'],phase_closed=r['phase_closed'],optimizer_success=r['optimizer_success'],
                    base_gate_failures=len(r['failed_gates']),exact_gate_pass=all(e['all_pass'] for e in r['exact']),lost=len(r['lost_ids']),reassigned=len(r['reassigned_ids']),incidental_added=len(r['added_ids'])))
        for constrained in (False,True):
            full=[t for t in trials if t['weight']==1 and t['constrained']==constrained]
            for policy in POLICIES:
                qualified=[]
                for t in full:
                    new=t['new_norad'];pair={a:best(t,a) for a in ARMS}
                    existing=set(before['fitted_c'].values());after=(existing-{old})|{new}
                    # Common age terms cancel. Do not charge the same satellite twice when merging.
                    removed=existing-after;added=after-existing
                    penalty=0. if new==old else sum(age_penalty(ages[n],policy) for n in added)-sum(age_penalty(ages[n],policy) for n in removed)
                    if policy=='hard48' and ages[new]>48:penalty=float('inf')
                    pair_ok=all(pair.values())
                    gains={a:base[a]['objective']-pair[a]['objective']-penalty if pair[a] else None for a in ARMS}
                    improves=pair_ok and all(gains[a]>1e-3 for a in ARMS)
                    for a in ARMS:
                        r=best(t,a,False)
                        age_rows.append(dict(case=case,norad=new,constrained=constrained,policy=policy,arm=a,age_h=ages[new],
                            penalty_delta=penalty if np.isfinite(penalty) else 'ineligible',paired_screen_pass=pair_ok,paired_improvement=improves,
                            error_km=r['error_m']/1000,rf_score=r['objective'],penalized_gain=gains[a] if gains[a] is not None and np.isfinite(gains[a]) else None))
                    if improves:qualified.append((sum(pair[a]['objective']+penalty for a in ARMS),t,pair,penalty))
                chosen=min(qualified,key=lambda q:q[0]) if qualified else None
                for a in ARMS:
                    r=chosen[2][a] if chosen else None
                    selected.append(dict(case=case,constrained=constrained,policy=policy,arm=a,norad=chosen[1]['new_norad'] if chosen else old,
                        error_km=r['error_m']/1000 if r else base[a]['error_m']/1000,changed=bool(chosen and chosen[1]['new_norad']!=old),
                        fallback=chosen is None,rf_gain=base[a]['objective']-r['objective'] if r else 0.,penalty_delta=chosen[3] if chosen else 0.,
                        associated_points=len(before[a]),associated_pct=100*len(before[a])/denom,
                        reassigned=len(r['reassigned_ids']) if r else 0,incidental_proposed_additions=len(r['added_ids']) if r else 0,
                        residual_rms_hz=r['rms_hz'] if r else None))
    dump_csv(OUT/'trials.csv',flat);dump_csv(OUT/'age_comparison.csv',age_rows);dump_csv(OUT/'selected.csv',selected);write(OUT/'provenance.json',meta)
    # Matched c-arm RF-selected results; original ownership inventory frozen.
    fig,axs=plt.subplots(1,2,figsize=(12,4.5),sharey=True)
    for ax,a in zip(axs,ARMS):
        x=np.arange(len(CASES));width=.24
        vals=[[data[c]['base'][a]['error_m']/1000 for c in CASES]]
        for constrained in (False,True):
            vals.append([next(r['error_km'] for r in selected if r['case']==c and r['arm']==a and r['policy']=='none' and r['constrained']==constrained) for c in CASES])
        for k,(v,label) in enumerate(zip(vals,['Published ALGO06','Reconsider identity','Reconsider + gate constraints'])):
            bars=ax.bar(x+(k-1)*width,v,width,label=label)
            for b,q in zip(bars,v):ax.text(b.get_x()+b.get_width()/2,q+.08,f'{q:.2f}',ha='center',fontsize=8)
        ax.set_xticks(x,[c[-4:] for c in CASES]);ax.set_xlabel('DS26 scan');ax.set_title('c = 0' if a=='c0' else 'Fitted c');ax.grid(axis='y',alpha=.2)
    axs[0].set_ylabel('Position error (km)');axs[1].legend(fontsize=8)
    fig.suptitle('Four outlier stress tests: RF-selected, paired-screened updates; fallback on rejection')
    fig.tight_layout();fig.savefig(OUT/'position_comparison.png',dpi=170);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,4.5));hours=np.linspace(0,72,400)
    for policy,label in zip(POLICIES[1:4],LABELS[1:4]):axs[0].plot(hours,[age_penalty(h,policy) for h in hours],label=label)
    axs[0].axvline(48,color='k',ls=':',label='Hard cutoff excludes >48h');axs[0].set(xlabel='Causal TLE age (hours)',ylabel='Added −2 log prior per satellite',title='Predeclared freshness penalties');axs[0].legend(fontsize=8)
    for case in CASES:
        row=[next(r for r in selected if r['case']==case and r['arm']=='fitted_c' and r['policy']==p and r['constrained']) for p in POLICIES]
        axs[1].plot(np.arange(5),[r['error_km'] for r in row],'-o',label=case[-4:])
    axs[1].set_xticks(np.arange(5),LABELS,rotation=20,ha='right');axs[1].set(ylabel='Position error (km)',title='Identity reconsideration + gate constraints');axs[1].legend(title='DS26 scan');axs[1].grid(alpha=.2)
    fig.tight_layout();fig.savefig(OUT/'age_penalties.png',dpi=170);plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(11,8),sharex=True)
    for ax,case in zip(axs.flat,CASES):
        old=SUSPECT[case]
        for arm,col in [('c0','tab:blue'),('fitted_c','tab:orange')]:
            for new in sorted({t['new_norad'] for t in data[case]['trials']}):
                rows=[next(t for t in data[case]['trials'] if t['new_norad']==new and t['weight']==w and not t['constrained']) for w in [1,.5,.25]]
                points=[best(t,arm,False) for t in rows]
                ax.plot([1,.5,.25],[r['error_m']/1000 for r in points],color=col,ls='-' if new==old else '--',alpha=.65,label=f'{arm}: {new}')
                for w,t,r in zip([1,.5,.25],rows,points):
                    q=best(t,arm);ax.scatter(w,r['error_m']/1000,color=col,marker='o' if q else 'x',s=45)
        ax.set(title=case,ylabel='Position error (km)');ax.legend(fontsize=7,ncol=2);ax.grid(alpha=.2)
    for ax in axs[-1]:ax.set_xlabel('Suspect family likelihood power')
    fig.suptitle('Downweighting stress test: × rejected; ○ at least one screened start\nDo not rank different powers by their training objective')
    fig.tight_layout();fig.savefig(OUT/'weight_sensitivity.png',dpi=170);plt.close(fig)
    # Candidate penalties required to reverse a preferred older identity.
    cross=[]
    for case in CASES:
        s=next(r for r in selected if r['case']==case and r['policy']=='none' and r['constrained'] and r['arm']=='fitted_c')
        for policy in POLICIES[1:4]:
            q=next(r for r in age_rows if r['case']==case and r['norad']==s['norad'] and r['policy']==policy and r['constrained'] and r['arm']=='fitted_c')
            penalty=q['penalty_delta']
            cross.append(dict(case=case,new_norad=s['norad'],policy=policy,rf_gain=s['rf_gain'],penalty_delta=penalty,
                multiplier_to_erase_gain=s['rf_gain']/penalty if isinstance(penalty,(int,float)) and penalty>0 else None))
    dump_csv(OUT/'penalty_crossovers.csv',cross)
    fallback=[]
    fig,axs=plt.subplots(1,2,figsize=(10,4),sharex=True)
    for ax,(case,n) in zip(axs,[('DS26-0251',58787),('DS26-0070',63571)]):
        for arm,col in [('c0','tab:blue'),('fitted_c','tab:orange')]:
            points=[]
            for factor in (1,2,4):
                path=OUT/case/(f'{n}-w1-constrained.json' if factor==1 else f'fallback-prior-{n}-x{factor}.json')
                t=read(path);r=best(t,arm,False);valid=best(t,arm)
                points.append(r['error_m']/1000)
                fallback.append(dict(case=case,norad=n,arm=arm,factor=factor,error_km=r['error_m']/1000,objective=r['objective'],screened=valid is not None,
                    lost=len(r['lost_ids']),failed_gates=len(r['failed_gates']),phase_closed=r['phase_closed']))
                ax.scatter(factor,r['error_m']/1000,c=col,marker='o' if valid else 'x',s=55)
            ax.plot([1,2,4],points,c=col,label=arm)
        ax.set(title=f'{case}: candidate {n}',xlabel='Missing-history phase SD multiplier',ylabel='Position error (km)');ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Fallback-prior sensitivity: ○ screened; × rejected. Same observations and constraints.')
    fig.tight_layout();fig.savefig(OUT/'fallback_prior.png',dpi=170);plt.close(fig)
    dump_csv(OUT/'fallback_prior.csv',fallback)
    write(OUT/'summary.json',dict(selected=selected,penalty_crossovers=cross,trial_count=len(flat),case_count=len(CASES)))
    print(json.dumps([r for r in selected if r['constrained'] and r['policy']=='none'],indent=2))

if __name__=='__main__':main()
