"""Render sealed conditional comparisons; GPS is read only here for evaluation."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from evidence import age_penalty
ROOT=Path(__file__).resolve().parent
TRUTH=(37.849061591561885,-122.48574968092912)


def read(p):return json.loads(Path(p).read_text())


def csvfile(path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with open(path,'w') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        w.writerows({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in rows)


def error(latlon):
    a,b=np.deg2rad(TRUTH),np.deg2rad(latlon)
    h=np.sin((b[0]-a[0])/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin((b[1]-a[1])/2)**2
    return float(2*6371.0088*np.arcsin(np.sqrt(h)))


def main():
    studies=[read(p) for p in sorted((ROOT/'cases').glob('*/*.json')) if p.name!='failure.json']
    assert len(studies)==20
    rows=[];summaries=[];sensitivity=[]
    for z in studies:
        rows+=z['candidate_rows']
        for s in z['summaries']:
            w=s['winner'];summaries.append(dict(case=w['case'],fragment_id=w['fragment_id'],receiver=z['source']['receiver'],channel=z['source']['channel'],points=z['source']['points'],**{k:w[k] for k in ['arm','policy','norad','age_h','score','likelihood_score','recency_penalty','rms_hz','phase_s','rate_hz_s','physical_screen_pass','integration_penalty']},margin=s['margin'],fold_winners=[f['norad'] for f in s['training_fold_winners']]))
        for arm in ['c0','fitted_c']:
            candidates=[r for r in z['candidate_rows'] if r['arm']==arm and r['policy']=='72_age_scaled']
            for life in [12.,24.,48.]:
                ranked=sorted(candidates,key=lambda r:r['score']+age_penalty(r['age_h'],life))
                sensitivity.append(dict(case=z['source']['case'],fragment_id=z['source']['fragment_id'],arm=arm,half_life_h=life,norad=ranked[0]['norad'],margin=ranked[1]['score']+age_penalty(ranked[1]['age_h'],life)-ranked[0]['score']-age_penalty(ranked[0]['age_h'],life)))
    csvfile(ROOT/'candidate_scores.csv',rows);csvfile(ROOT/'association_summary.csv',summaries);csvfile(ROOT/'recency_sensitivity.csv',sensitivity)
    fig,axs=plt.subplots(1,3,figsize=(16,9),layout='constrained');labels=[]
    for k,z in enumerate(studies):
        selected={s['policy']:s for s in z['summaries'] if s['arm']=='fitted_c'};old=selected['48_fixed']['winner'];new=selected['72_age_scaled_recency24']['winner']
        labels.append(f"{z['source']['case']} RX{z['source']['receiver']} CH{z['source']['channel']} ({z['source']['points']})")
        axs[0].plot([old['rms_hz'],new['rms_hz']],[k,k],color='0.65');axs[0].scatter(old['rms_hz'],k,color='gray',s=28);axs[0].scatter(new['rms_hz'],k,color='#196b9a',s=30)
        axs[1].barh(k,old['score']-new['score'],color='#196b9a' if old['norad']!=new['norad'] else '#b4c5cf')
        axs[2].scatter(new['age_h'],k,color='#c36227' if new['age_h']>48 else '#196b9a');axs[2].annotate(str(new['norad']),(new['age_h'],k),xytext=(6,0),textcoords='offset points',va='center',fontsize=8)
    axs[0].set_yticks(range(20),labels,fontsize=9);axs[0].set_xscale('log');axs[0].set_xlabel('Residual RMS (Hz), log scale');axs[0].set_title('Gray: 48 h; blue: 72 h + priors')
    axs[1].set_xscale('symlog',linthresh=1);axs[1].set_xlabel('Reduction in −2 log score');axs[1].set_title('Positive favors 72-hour model')
    axs[2].axvline(48,color='#b04020',ls='--');axs[2].set(xlim=(0,80),xlabel='Winning TLE age (hours)',title='Winning satellite identity')
    for ax in axs:ax.set_ylim(19.7,-.7);ax.grid(axis='x',alpha=.2)
    for ax in axs[1:]:ax.set_yticks(range(20),['']*20)
    fig.suptitle('Twenty audited residual sources: normalized evidence with a causal 72-hour fallback\nFitted-c arm; fixed inherited receiver calibration and published positions; diagnostic rankings',fontsize=14)
    fig.savefig(ROOT/'twenty_source_comparison.png',dpi=170);plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(14,8),layout='constrained')
    for col,case in enumerate(['DS26-0062','DS26-0068']):
        z=next(z for z in studies if z['source']['case']==case);fid=z['source']['fragment_id'];a=np.load(ROOT/'cases'/case/(fid+'.npz'))
        s={v['policy']:v['winner'] for v in z['summaries'] if v['arm']=='fitted_c'};t=a['times_s'];radio=a['values_hz']-a['fitted_c_corrected_hz']
        axs[0,col].scatter(t,a['values_hz']/1000,color='black',s=15,label='Native GLRT, saved unwrapped branch')
        for name,color in [('48_fixed','gray'),('72_age_scaled_recency24','#1478ab')]:
            w=s[name];key=f'fitted_c_{name}_{w["norad"]}';pred=a[key+'_prediction']+radio
            axs[0,col].plot(t,pred/1000,color=color,label=f"{name}: {w['norad']}")
            axs[1,col].plot(t,a[key+'_residual'],'.-',color=color,label=f"{w['norad']}: {w['rms_hz']:.1f} Hz RMS")
        axs[0,col].set(title=f"{case} RX{z['source']['receiver']} CH{z['source']['channel']}",ylabel='Unwrapped GLRT CFO (kHz)');axs[0,col].legend(fontsize=8)
        axs[1,col].axhline(0,color='black',lw=.8);axs[1,col].set(xlabel='Scan time (s)',ylabel='Residual (Hz)');axs[1,col].legend(fontsize=9)
    for ax in axs.flat:ax.grid(alpha=.2)
    fig.suptitle('The two age-excluded identities: full native-point curves, with unchanged residual checks',fontsize=14)
    fig.savefig(ROOT/'older_candidate_curves.png',dpi=170);plt.close(fig)
    local=[]
    for case in ['DS26-0062','DS26-0068']:
        p=ROOT/'local_inclusion'/case/'result.json'
        if not p.exists():continue
        data=read(p);base=read(Path('/srv/bulk/leo/research/ds26-confident-recovery-20261031/baselines')/(case+'.json'))
        denom=len(set(base['observation_ids']))
        for variant,pair in data.items():
            pair_pass=all(v['all_checked_gates_pass'] for v in pair.values())
            for arm,v in pair.items():
                target=v.get('target');old=len(base['owners'][arm]);added=v.get('proposed_added_points',0)
                local.append(dict(case=case,variant=variant,arm=arm,error_km=error(v['endpoint_latlon']),
                    latitude=v['endpoint_latlon'][0],longitude=v['endpoint_latlon'][1],
                    baseline_associated=old,total_native_GLRT=denom,proposed_added_points=added,
                    baseline_association_pct=100*old/denom,proposed_association_pct=100*(old+added)/denom,
                    pair_checked_gates_pass=pair_pass,individual_checked_gates_pass=v['all_checked_gates_pass'],
                    failed_checks=[k for k,b in v['checks'].items() if not b],
                    changed_incumbent_points=len(v['changed_incumbent_ids']),
                    target_rms_hz=None if target is None else target['diagnostics'][0]['profile_RMS_hz'],
                    target_phase_s=None if target is None else target['phase_map_s'],
                    target_noise=None if target is None else target['diagnostics'][0]['noise'],
                    phase_prior_sigma_s=None if target is None else read(p.parent/'protocol.json')['scaled_prior' if 'scaled' in variant else 'original_prior']['phase_prior_sigma_s'],
                    production_added_points=0))
    csvfile(ROOT/'local_position_evaluation.csv',local)
    fig,axs=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    variants=['control','72_original_physical_prior','72_age_scaled_physical_prior']
    for ax,case in zip(axs,['DS26-0062','DS26-0068']):
        for i,arm in enumerate(['c0','fitted_c']):
            v=[next(r for r in local if r['case']==case and r['arm']==arm and r['variant']==name) for name in variants]
            bars=ax.bar(np.arange(3)+(i-.5)*.33,[r['error_km'] for r in v],width=.3,color=['#68839b','#6b36a1'][i],label=arm)
            for b,r in zip(bars,v):
                if not r['pair_checked_gates_pass']:b.set_hatch('///');b.set_alpha(.5)
                ax.text(b.get_x()+b.get_width()/2,b.get_height()+.008,f"{r['error_km']:.3f}",ha='center',fontsize=9)
        ax.set_xticks(range(3),['Matched\ncontrol','72 h + original\nphysical prior','72 h + wider\nphase prior']);ax.set(title=case,ylabel='Position error (km)');ax.legend();ax.grid(axis='y',alpha=.2);ax.set_ylim(0,max(r['error_km'] for r in local if r['case']==case)*1.25)
    fig.suptitle('Conditional local position probes: hatched bars fail inclusion checks\nGPS used only for this downstream evaluation; no production associations changed',fontsize=12)
    fig.savefig(ROOT/'local_position_error.png',dpi=170);plt.close(fig)
    overview=dict(sources=len(studies),native_points=sum(z['source']['points'] for z in studies),candidate_policy_arm_rows=len(rows),
                  shortlist_candidates=sum(len(z['shortlist_norads']) for z in studies),
                  changed_identities={arm:sum(next(s for s in z['summaries'] if s['arm']==arm and s['policy']=='48_fixed')['winner']['norad']!=next(s for s in z['summaries'] if s['arm']==arm and s['policy']=='72_age_scaled_recency24')['winner']['norad'] for z in studies) for arm in ['c0','fitted_c']},
                  recency_half_life_winners_stable=all(len({r['norad'] for r in sensitivity if r['case']==z['source']['case'] and r['fragment_id']==z['source']['fragment_id'] and r['arm']==arm})==1 for z in studies for arm in ['c0','fitted_c']),
                  GPS_evaluation_only=True,production_added_points=0)
    (ROOT/'summary.json').write_text(json.dumps(overview,indent=2)+'\n')
    print(json.dumps(overview,indent=2))
    for r in local:print(r['case'],r['variant'],r['arm'],round(r['error_km'],4),r['pair_checked_gates_pass'],r['target_rms_hz'],r['failed_checks'])


if __name__=='__main__':main()
