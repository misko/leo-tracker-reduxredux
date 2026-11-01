"""Report paired complete-cohort outcomes; never change inference decisions."""
import csv
import hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import evaluate as e

LABELS={'ALGO06':'ALGO06','history_only':'History only','reassociation_only':'Reassociation only','combined':'Combined'}
COLORS={'ALGO06':'#252525','history_only':'#2a9d8f','reassociation_only':'#e18c23','combined':'#4967cb'}


def table(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)


def main():
    protocol=e.read(e.OUT/'protocol.json');positions=[];decisions=[];availability=[];attempts=[];history=[]
    earlier=e.read(e.PRIOR/'protocol.json')
    exposed=set(earlier['development']+earlier['validation'])
    for item in protocol['cohort']:
        case=item['case'];folder=e.OUT/case;path=folder/'result.json'
        if not path.exists():
            availability.append(dict(case=case,status='incomplete',reason='No completed result; excluded from numerical comparisons, retained in roster'));continue
        result=e.read(path);availability.append(dict(case=case,status=result.get('execution_status','complete'),seconds=result['seconds']))
        z=e.read(e.ROOTS[case[:4]]/'inputs'/(case+'.json'));total=len(e.read(Path(z['native_path'])/'observations.json'))
        history.append(dict(case=case,requested=len(result['history']['requested']),available=len(result['history']['available']),missing=len(result['history']['missing'])))
        for method,values in result['methods'].items():
            for a in e.ARMS:
                b=result['baseline'][a];r=values['final'][a]
                positions.append(dict(case=case,dataset=case[:4],stage=item['stage'],arm=a,method=method,selected=values['selected'],
                    execution_status=result.get('execution_status','complete'),
                    prior_prototype_exposure=case in exposed,
                    baseline_m=b['error_m'],error_m=r['error_m'],delta_m=r['error_m']-b['error_m'],objective=r['objective'],baseline_objective=b['objective'],
                    rms_hz=r['rms_hz'],baseline_rms_hz=b['rms_hz'],associated=r['associated'],total=total,associated_pct=100*r['associated']/total,
                    changed=values['selected'] is not None,seconds=result['seconds']))
        for method,records in result['records'].items():
            for r in records:
                decisions.append(dict(case=case,method=method,name=r['name'],accepted=r['accepted'],selected=result['methods'][method]['selected']==r['name'],
                    gain_c0=r.get('gains',{}).get('c0'),gain_fitted=r.get('gains',{}).get('fitted_c'),reason=r.get('reason'),
                    complete_c0=r.get('pair',{}).get('c0') is not None,complete_fitted=r.get('pair',{}).get('fitted_c') is not None))
        fit_paths=list(folder.glob('**/*fits.json'))+list(folder.glob('**/control_*.json'))+list(folder.glob('history_control.json'))+list(folder.glob('history_candidate.json'))
        for fits in sorted(set(fit_paths)):
            if 'diagnostics' in fits.parts:continue
            for r in e.read(fits):
                attempts.append(dict(case=case,path=str(fits.relative_to(e.OUT)),arm=r['arm'],start=r['start'],status=r['status'],qualified=r['qualified'],
                    objective=r.get('objective'),error_m=r.get('error_m'),seconds=r.get('seconds'),reason=r.get('reason'),
                    failed_gates=len(r.get('failed_gates',{})),phase_closed=r.get('phase_closed'),optimizer_success=r.get('optimizer_success'),
                    lost=len(r.get('lost_ids',[])),reassigned=len(r.get('reassigned_ids',[]))))
    availability += [dict(case=c,status='upstream_unavailable',reason='No usable matched ALGO06 baseline in frozen DS28 roster') for c in protocol['unavailable_validation']]
    upstream=e.read(e.ROOTS['DS26']/'protocol.json')['unavailable']
    availability += [dict(case=r['case'],status='upstream_unavailable',reason=r['reason']) for r in upstream]
    table(e.OUT/'positions.csv',positions);table(e.OUT/'decisions.csv',decisions);table(e.OUT/'availability.csv',availability);table(e.OUT/'attempts.csv',attempts);table(e.OUT/'history_inventory.csv',history)
    metrics=[]
    for dataset in ('DS26','DS27','DS28','DS26+DS27','new_to_rule'):
        for arm in e.ARMS:
            for method in e.METHODS:
                rows=[r for r in positions if ((r['dataset'] in ('DS26','DS27') and not r['prior_prototype_exposure']) if dataset=='new_to_rule' else r['dataset'] in dataset.split('+')) and r['arm']==arm and r['method']==method]
                if not rows:continue
                err=np.array([r['error_m'] for r in rows]);d=np.array([r['delta_m'] for r in rows])
                bootstrap=np.mean(np.random.default_rng(20261104).choice(d,(5000,len(d)),replace=True),axis=1)
                metrics.append(dict(dataset=dataset,arm=arm,method=method,n=len(rows),mean_m=float(err.mean()),median_m=float(np.median(err)),
                    p90_m=float(np.quantile(err,.9)),p95_m=float(np.quantile(err,.95)),max_m=float(err.max()),within500=int(sum(err<=500)),
                    mean_delta_m=float(d.mean()),bootstrap_mean_delta_low_m=float(np.quantile(bootstrap,.025)),bootstrap_mean_delta_high_m=float(np.quantile(bootstrap,.975)),
                    changed=sum(r['changed'] for r in rows),improved25=int(sum(d< -25)),regressed25=int(sum(d>25)),max_regression_m=float(max(0,d.max())),
                    max_improvement_m=float(max(0,-d.min())),associated_pct=100*sum(r['associated'] for r in rows)/sum(r['total'] for r in rows)))
    table(e.OUT/'summary.csv',metrics)
    funnel=[]
    for dataset in ('DS26','DS27','DS28'):
        cases=[e.read(p) for p in e.OUT.glob(dataset+'-*/result.json')]
        screens=[e.read(p) for p in e.OUT.glob(dataset+'-*/*/screen.json')]
        proposals=[h for s in screens for h in s.get('proposals',[]) if 'prediction_limit' not in h]
        funnel.append(dict(dataset=dataset,outcomes=len(cases),triggered_scans=sum(bool(r['targets']) for r in cases),
            screened_families=len(screens),screened_normally=sum(s['status']=='screened' for s in screens),
            whole_family_proposals=len(proposals),predictive_pass=sum(all(h['predictive'][a]['pass_check'] for a in e.ARMS) for h in proposals),
            reassociation_only_accepted=sum(r['methods']['reassociation_only']['selected'] is not None for r in cases),
            combined_identity_changes=sum(r['methods']['combined']['selected'] not in (None,'complete_history') for r in cases),
            history_only_accepted=sum(r['methods']['history_only']['selected'] is not None for r in cases)))
    table(e.OUT/'search_funnel.csv',funnel)
    e.write(e.OUT/'summary.json',dict(metrics=metrics,availability=availability,decisions=decisions,history=history,funnel=funnel,attempt_count=len(attempts),complete_attempts=sum(r['status']=='complete' for r in attempts)))
    fig,axs=plt.subplots(2,3,figsize=(15,8),layout='constrained')
    for i,arm in enumerate(e.ARMS):
        for j,dataset in enumerate(('DS26','DS27','DS28')):
            ax=axs[i,j]
            for k,method in enumerate(e.METHODS):
                xx=np.sort([r['error_m']/1000 for r in positions if r['arm']==arm and r['dataset']==dataset and r['method']==method])
                if not len(xx):continue
                ax.step(xx,np.arange(1,len(xx)+1)/len(xx),where='post',label=LABELS[method],color=COLORS[method],linestyle=['-',':','--','-.'][k],linewidth=1.8)
            n=sum(r['arm']==arm and r['dataset']==dataset and r['method']=='ALGO06' for r in positions)
            ax.set_title(dataset+' / '+arm+f' / n={n}');ax.set_xlabel('Position error (km)');ax.set_ylabel('Fraction of available outcomes');ax.axvline(.5,color='#999999',linestyle=':',linewidth=.7);ax.grid(alpha=.2)
    axs[0,0].legend(fontsize=8);fig.suptitle('Frozen causal evaluation: all available scans; GPS used only for error reporting\nDS28 is a separate validation cohort; unchanged curves can coincide')
    fig.savefig(e.OUT/'error_cdf.png',dpi=165);plt.close(fig)
    changed=[r for r in positions if r['changed'] and r['method']!='ALGO06'];cases=sorted({r['case'] for r in changed})
    if cases:
        fig,axs=plt.subplots(1,2,figsize=(13,max(4,.4*len(cases))),sharey=True,layout='constrained')
        for ax,arm in zip(axs,e.ARMS):
            for k,method in enumerate(e.METHODS):
                rows=[next(r for r in positions if r['case']==c and r['arm']==arm and r['method']==method) for c in cases]
                ax.scatter([r['error_m']/1000 for r in rows],np.arange(len(cases))+(k-1.5)*.14,s=28,label=LABELS[method],color=COLORS[method],marker=['o','s','^','D'][k])
            ax.set_yticks(range(len(cases)),cases);ax.set_xlabel('Position error (km)');ax.set_title(arm);ax.grid(alpha=.2);ax.legend(fontsize=8)
        axs[0].invert_yaxis();fig.suptitle('Every scan with an accepted change; all methods shown');fig.savefig(e.OUT/'changed_scans.png',dpi=170);plt.close(fig)
        fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
        for ax,arm in zip(axs,e.ARMS):
            for method in e.METHODS[1:]:
                rows=[r for r in changed if r['arm']==arm and r['method']==method]
                ax.scatter([r['baseline_objective']-r['objective'] for r in rows],[r['delta_m'] for r in rows],label=LABELS[method],color=COLORS[method],s=38)
                for r in rows:ax.annotate(r['case'],(r['baseline_objective']-r['objective'],r['delta_m']),fontsize=6,xytext=(3,3),textcoords='offset points')
            ax.axhline(0,color='black',lw=.8);ax.set_xlabel('Normalized RF score gain vs published endpoint');ax.set_ylabel('Position error change (m; negative is better)');ax.set_title(arm);ax.grid(alpha=.2);ax.legend(fontsize=8)
        fig.suptitle('Frequency-fit improvement is evaluated separately from localization');fig.savefig(e.OUT/'score_vs_accuracy.png',dpi=165);plt.close(fig)
    transfer=[];sensitivity=[]
    for path in sorted(e.OUT.glob('DS*/diagnostics/result.json')):
        for result in e.read(path):
            case=result['case'];method=result['method']
            for r in result['sensitivity']:sensitivity.append(dict(case=case,variant=method,**r))
            for a in e.ARMS:
                for rx in (1,2):
                    before=next((r for r in result['transfer'] if r['arm']==a and r['receiver']==rx and r['context']=='incumbent' and r['status']=='complete'),None)
                    after=next((r for r in result['transfer'] if r['arm']==a and r['receiver']==rx and r['context']=='replacement' and r['status']=='complete'),None)
                    if before and after:transfer.append(dict(case=case,method=method,arm=a,receiver=rx,before_rms_hz=before['rms_hz'],after_rms_hz=after['rms_hz'],
                        predictive_gain=before['score']-after['score'],both_phase_closed=before['phase_closed'] and after['phase_closed'],held_points=after['held_points']))
            rows=[r for r in result['native'] if r['arm']=='fitted_c']
            if rows:
                fig,axs=plt.subplots(len(rows),2,figsize=(12,max(3,2*len(rows))),squeeze=False,layout='constrained')
                for axes,r in zip(axs,rows):
                    t=np.array(r['times_s']);v=np.array(r['values_hz']);old=np.array(r['old_residual_hz']);new=np.array(r['residual_hz'])
                    axes[0].scatter(t,v/1000,s=9,c='black',label='Native fitted GLRT')
                    axes[0].plot(t,(v-old)/1000,label='ALGO06 adjusted orbit',color='#777777')
                    axes[0].plot(t,(v-new)/1000,label='Replacement adjusted orbit',color=COLORS[method])
                    axes[0].set_title(f"RX{r['receiver']} CH{r['channel']}, {len(t)} points");axes[0].set_ylabel('Alias-lifted CFO (kHz)')
                    axes[1].plot(t,old,'.-',color='#777777',label='ALGO06');axes[1].plot(t,new,'.-',color=COLORS[method],label='Replacement');axes[1].axhline(0,color='black',lw=.7);axes[1].set_ylabel('Full-fit residual (Hz)')
                    for ax in axes:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
                axs[0,0].legend(fontsize=7);axs[0,1].legend(fontsize=7)
                fig.suptitle(case+' / '+method+' / '+result['selected']+'\nAdjusted orbit includes fitted radio and orbital terms; these residuals are in-sample')
                fig.savefig(e.OUT/(case+'-'+method+'-curves.png'),dpi=145);plt.close(fig)
    table(e.OUT/'transfer.csv',transfer);table(e.OUT/'sensitivity.csv',sensitivity)
    if transfer:
        rows=[r for r in transfer if r['arm']=='fitted_c']
        fig,axs=plt.subplots(1,2,figsize=(14,max(4,.28*len(rows))),sharey=True,layout='constrained')
        labels=[r['case']+' '+r['method']+' RX'+str(r['receiver'])+(' *' if not r['both_phase_closed'] else '') for r in rows];yy=np.arange(len(rows))
        axs[0].scatter([r['before_rms_hz'] for r in rows],yy,label='Incumbent',c='#555555');axs[0].scatter([r['after_rms_hz'] for r in rows],yy,label='Replacement',c='#4967cb')
        axs[0].set_xlabel('Held-receiver RMS (Hz)');axs[0].legend();axs[0].set_yticks(yy,labels);axs[0].invert_yaxis()
        axs[1].barh(yy,[r['predictive_gain'] for r in rows],color=['#2a9d8f' if r['predictive_gain']>0 else '#d35e60' for r in rows]);axs[1].axvline(0,color='black',lw=.8);axs[1].set_xlabel('Conditional predictive gain; positive favors replacement')
        fig.suptitle('Predict held target tracks on one receiver from remaining curved evidence\nTraining-only phase refresh; * means phase failed closure, not valid predictive support')
        fig.savefig(e.OUT/'receiver_transfer.png',dpi=150);plt.close(fig)
    track_transfer=[]
    for path in sorted(e.OUT.glob('DS*/whole_track_transfer.json')):
        result=e.read(path)
        for before in result['rows']:
            if before['context']!='incumbent' or before['status']!='complete':continue
            after=next((r for r in result['rows'] if r['method']==before['method'] and r['arm']==before['arm'] and r['split']==before['split'] and r['context']=='replacement' and r['status']=='complete'),None)
            if after:track_transfer.append(dict(case=result['case'],method=before['method'],arm=before['arm'],component=before['split'],
                before_rms_hz=before['rms_hz'],after_rms_hz=after['rms_hz'],predictive_gain=before['score']-after['score'],
                both_phase_closed=before['phase_closed'] and after['phase_closed'],held_points=after['held_points']))
    table(e.OUT/'whole_track_transfer.csv',track_transfer)
    if track_transfer:
        rr=[r for r in track_transfer if r['arm']=='fitted_c'];fig,axs=plt.subplots(1,2,figsize=(14,max(4,.24*len(rr))),sharey=True,layout='constrained');yy=np.arange(len(rr))
        axs[0].scatter([r['before_rms_hz'] for r in rr],yy,color='#777777',label='Incumbent');axs[0].scatter([r['after_rms_hz'] for r in rr],yy,color='#4967cb',label='Replacement')
        axs[0].set_yticks(yy,[r['case']+' '+r['method']+' '+r['component'].split('-RF')[0].replace('SCAN-','') for r in rr]);axs[0].invert_yaxis();axs[0].set_xlabel('Held whole-track RMS (Hz)');axs[0].legend()
        axs[1].barh(yy,[r['predictive_gain'] for r in rr],color=['#2a9d8f' if r['predictive_gain']>0 else '#d35e60' for r in rr]);axs[1].axvline(0,color='black',lw=.8);axs[1].set_xlabel('Conditional predictive gain; positive favors replacement')
        fig.suptitle('Whole-track transfer, fitted c\nFixed RF cavity position; training-only phase refresh; inherited graph/alias/discovery choices');fig.savefig(e.OUT/'whole_track_transfer.png',dpi=145);plt.close(fig)
    e.write(e.OUT/'diagnostic_summary.json',dict(transfer=transfer,sensitivity=sensitivity,whole_track_transfer=track_transfer))
    print('Completed scans:',sum(r['status']=='complete' for r in availability),'Changed:',cases)
    for m in metrics:print(m)


if __name__=='__main__':main()
