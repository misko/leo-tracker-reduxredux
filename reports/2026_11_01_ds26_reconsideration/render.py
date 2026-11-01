"""Render all predeclared cases; preserve nulls and fallback explicitly."""
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reconsider import OUT,INPUT,ARMS,DEVELOP,read,write,reconstruct

def table(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
    protocol=read(OUT/'protocol.json');cases=protocol['development']+protocol['validation'];positions=[];trials=[];triggers=[]
    for case in cases:
        result=read(OUT/case/'result.json');z=read(INPUT/(case+'.json'));total=len(read(__import__('pathlib').Path(z['native_path'])/'observations.json'))
        for a in ARMS:
            positions.append(dict(case=case,cohort='development' if case in DEVELOP else 'validation',arm=a,selected=result['selected'],
                before_km=result['baseline'][a]['error_m']/1000,after_km=result['final'][a]['error_m']/1000,
                before_score=result['baseline'][a]['objective'],after_score=result['final'][a]['objective'],associated_points=result['final'][a]['associated'],total_glrt=total,associated_pct=100*result['final'][a]['associated']/total))
        for r in read(OUT/case/'trigger.json')['ranking']:
            triggers.append(dict(case=case,norad=r['norad'],points=r['points'],tracks=r['tracks'],influence_km=r['rank_score'],selected=r['norad'] in result['triggered']))
        for rec in result['records']:
            h=rec['hypothesis']
            for r in rec['rows']:
                trials.append(dict(case=case,hypothesis=h['name'],arm=r['arm'],start=r['start'],status=r['status'],qualified=r['qualified'],
                    predictive=h['predictive'][r['arm']]['pass_check'],partition_diagnostic='prediction_limit' in h,error_km=r.get('error_m',np.nan)/1000 if 'error_m' in r else None,
                    objective=r.get('objective'),phase_closed=r.get('phase_closed'),optimizer_success=r.get('optimizer_success'),
                    failed_gates=len(r.get('failed_gates',{})) if 'failed_gates' in r else None,lost=len(r.get('lost_ids',[])) if 'lost_ids' in r else None,
                    reassigned=len(r.get('reassigned_ids',[])) if 'reassigned_ids' in r else None,seconds=r.get('seconds'),reason=r.get('reason',rec.get('error'))))
    table(OUT/'positions.csv',positions);table(OUT/'trials.csv',trials);table(OUT/'triggers.csv',triggers)
    metrics=[]
    for cohort in ('development','validation'):
        for a in ARMS:
            rows=[r for r in positions if r['cohort']==cohort and r['arm']==a]
            metrics.append(dict(cohort=cohort,arm=a,n=len(rows),changed=sum(r['selected'] is not None for r in rows),
                before_median_km=float(np.median([r['before_km'] for r in rows])),after_median_km=float(np.median([r['after_km'] for r in rows])),
                before_p90_km=float(np.quantile([r['before_km'] for r in rows],.9)),after_p90_km=float(np.quantile([r['after_km'] for r in rows],.9)),
                before_max_km=max(r['before_km'] for r in rows),after_max_km=max(r['after_km'] for r in rows)))
    write(OUT/'summary.json',dict(positions=positions,metrics=metrics,trial_count=len(trials),completed=sum(r['status']=='complete' for r in trials)))
    fig,axs=plt.subplots(1,2,figsize=(13,6),sharey=True,layout='constrained')
    for ax,a in zip(axs,ARMS):
        rows=[r for r in positions if r['arm']==a];yy=np.arange(len(rows))
        ax.hlines(yy,[r['before_km'] for r in rows],[r['after_km'] for r in rows],color='#777777')
        ax.scatter([r['before_km'] for r in rows],yy,label='ALGO06',facecolors='none',edgecolors='black',s=65)
        ax.scatter([r['after_km'] for r in rows],yy,label='Frozen reconsideration rule',color='#1469aa',s=28)
        ax.axhline(3.5,color='#888888',linestyle=':');ax.set_yticks(yy,[r['case']+(' [dev]' if r['cohort']=='development' else '') for r in rows]);ax.set_xlabel('Position error (km)');ax.set_title(a);ax.grid(alpha=.2);ax.legend(fontsize=9)
    axs[0].invert_yaxis()
    fig.suptitle('Four development outliers and eight randomly selected validation scans\nFallback preserves the published result when no replacement qualifies')
    fig.savefig(OUT/'positions.png',dpi=170);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,a in zip(axs,ARMS):
        rows=[r for r in positions if r['arm']==a and r['cohort']=='validation']
        for key,label,style in [('before_km','ALGO06','-'),('after_km','Reconsideration','--')]:
            xx=np.sort([r[key] for r in rows]);ax.step(xx,np.arange(1,len(xx)+1)/len(xx),where='post',label=label,linestyle=style)
        ax.set_title(a);ax.set_xlabel('Position error (km)');ax.set_ylabel('Fraction of eight scans');ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Random-scan validation; n=8, too small for a tail guarantee');fig.savefig(OUT/'validation_cdf.png',dpi=170);plt.close(fig)
    ablation=read(OUT/'DS26-0251/history_ablation.json');models=['fallback','phase_history','orbit_history','full_history'];selected=[]
    fig,ax=plt.subplots(figsize=(9,4),layout='constrained')
    for i,a in enumerate(ARMS):
        vals=[]
        for m in models:
            r=min([r for r in ablation['rows'] if r['arm']==a and r['model']==m and r.get('qualified')],key=lambda r:r['objective']);vals.append(r['error_m']/1000);selected.append(dict(model=m,arm=a,error_km=r['error_m']/1000,objective=r['objective'],rms_hz=r['rms_hz']))
        bars=ax.bar(np.arange(4)+(i-.5)*.35,vals,.35,label=a);ax.bar_label(bars,fmt='%.3f',fontsize=9)
    ax.set_xticks(range(4),['Fallback prior','Phase history only','Physical-mode history only','Full causal history']);ax.set_ylabel('Position error (km)');ax.set_title('0251: matched prior ablation for the same candidate 58787');ax.legend();fig.savefig(OUT/'history_ablation.png',dpi=170);plt.close(fig);table(OUT/'history_ablation.csv',selected)
    transfer=[];fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,case in zip(axs,['DS26-0251','DS26-0034']):
        result=read(OUT/case/'result.json');rec=next(r for r in result['records'] if r['hypothesis']['name']==result['selected']);old=rec['target'];new=rec['hypothesis']['norad']
        before=read(OUT/case/'transfer_refreshed.json')['rows'];after=read(OUT/case/'transfer_selected_refreshed.json')['rows']
        for a in ARMS:
            for name in ['whole_family','held_RX1','held_RX2']:
                x=next(r for r in before if r.get('score') is not None and r['target']==old and r['arm']==a and r['model']=='full' and r['split']==name)
                y=next(r for r in after if r.get('score') is not None and r['target']==new and r['arm']==a and r['model']=='full' and r['split']==name)
                transfer.append(dict(case=case,arm=a,split=name,old_norad=old,new_norad=new,before_rms_hz=x['rms_hz'],after_rms_hz=y['rms_hz'],predictive_gain=x['score']-y['score'],both_phase_closed=x['phase_closed'] and y['phase_closed'],held_points=y['held_points']))
        rows=[r for r in transfer if r['case']==case and r['arm']=='fitted_c' and r['split']!='whole_family']
        for i,(k,label) in enumerate([('before_rms_hz',str(old)),('after_rms_hz',str(new))]):
            bars=ax.bar(np.arange(2)+(i-.5)*.35,[r[k] for r in rows],.35,label=label);ax.bar_label(bars,fmt='%.0f')
        ax.set_xticks([0,1],['Predict RX1 from others','Predict RX2 from others']);ax.set_ylabel('Held-track RMS (Hz)');ax.set_title(case+'; fitted c');ax.legend(title='Satellite hypothesis')
    fig.suptitle('Train on other tracks; refresh phase using training data only\nPosition fixed at RF-only whole-family omission fit; conditional diagnostic')
    fig.savefig(OUT/'receiver_transfer.png',dpi=170);plt.close(fig);table(OUT/'receiver_transfer.csv',transfer)
    fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained');sensitivity=[]
    for ax,case in zip(axs,['DS26-0251','DS26-0034']):
        rows=read(OUT/case/'sensitivity.json')['rows'];base=read(OUT/case/'result.json')['final']
        for a in ARMS:
            rr=[next(r for r in rows if r['arm']==a and r['method']==m) for m in ['margin_001','margin_005']]
            ax.plot([0,.01,.05],[base[a]['error_m']/1000]+[r['error_m']/1000 for r in rr],'-o',label=a)
            for r in rows:
                if r['arm']==a:sensitivity.append(dict(case=case,arm=a,method=r['method'],error_km=r.get('error_m',np.nan)/1000,qualified=r.get('qualified'),margin_pass=r.get('margin_pass'),displacement_km=r.get('displacement_from_selected_km')))
        ax.set_title(case);ax.set_xlabel('Required normalized gate margin');ax.set_ylabel('Position error (km)');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('0251 stable to these gate perturbations; 0034 remains sensitive');fig.savefig(OUT/'gate_sensitivity.png',dpi=170);plt.close(fig);table(OUT/'sensitivity.csv',sensitivity)
    fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained');mixtures=[]
    for ax,case in zip(axs,['DS26-0251','DS26-0034']):
        rows=read(OUT/case/'phase_mixture.json')['rows']
        for a in ARMS:
            x=next(r for r in rows if r['context']=='incumbent' and r['arm']==a);y=next(r for r in rows if r['context']=='replacement' and r['arm']==a)
            gain=x['prior_predictive_score']-y['prior_predictive_score'];ax.bar(a,gain)
            mixtures.append(dict(case=case,arm=a,old_norad=x['norad'],new_norad=y['norad'],predictive_gain=gain,incumbent_phase_MAP=x['diagnostic_phase_map_s'],replacement_phase_MAP=y['diagnostic_phase_map_s'],prior_mass_old=x['included_prior_mass'],prior_mass_new=y['included_prior_mass']))
        ax.set_title(case);ax.set_ylabel('Held-family predictive gain');ax.axhline(0,color='black',lw=.8)
    fig.suptitle('Unknown target phase integrated over its causal prior\nPositive favors the replacement; conditional on searched identities and frozen RF position')
    fig.savefig(OUT/'whole_family_prediction.png',dpi=170);plt.close(fig);table(OUT/'phase_mixture.csv',mixtures)
    case='DS26-0251';result=read(OUT/case/'result.json');rec=next(r for r in result['records'] if r['hypothesis']['name']==result['selected'])
    fitted=min([r for r in rec['rows'] if r['arm']=='fitted_c' and r['qualified']],key=lambda r:r['objective'])
    target=[t for t in fitted['tracks'] if t['norad']==rec['hypothesis']['norad']]
    d=reconstruct(read(INPUT/(case+'.json')));p,x=d['problems']['fitted_c'];c=p.calculate(x);baseline={r['component']:c['conditional_residual_hz'][sl][p.keep[sl]] for r,sl in zip(p.rows,p.slices)}
    fig,axs=plt.subplots(len(target),2,figsize=(12,2.2*len(target)),layout='constrained')
    for axes,t in zip(axs,target):
        times=np.array(t['times_s']);v=np.array(t['values_hz']);res=np.array(t['residual_hz']);old=baseline[t['component']];ax,bx=axes
        ax.scatter(times,v/1000,s=10,color='black',label='Native fitted GLRT')
        ax.plot(times,(v-old)/1000,color='#1674bb',label='Published adjusted orbit: 56548')
        ax.plot(times,(v-res)/1000,color='#e27516',label='New adjusted orbit: 58787')
        ax.set_title(f"RX{t['receiver']} CH{t['channel']}: {len(times)} points");ax.set_ylabel('Alias-lifted CFO (kHz)')
        bx.plot(times,old,'.-',label='Published',color='#1674bb');bx.plot(times,res,'.-',label='Reconsidered',color='#e27516');bx.axhline(0,color='black',lw=.8);bx.set_ylabel('Full-fit residual (Hz)')
        for a in axes:a.set_xlabel('Scan time (s)');a.grid(alpha=.2)
    axs[0,0].legend(fontsize=8);axs[0,1].legend(fontsize=8)
    fig.suptitle('DS26-0251: same native curved points, new identity and causal-history prior\nAdjusted orbit includes receiver and orbital corrections; in-sample residuals, not predictive validation')
    fig.savefig(OUT/'native_curves_0251.png',dpi=155);plt.close(fig)
    print(metrics)

if __name__=='__main__':main()
