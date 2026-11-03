"""Replay RF proposals and real paired positions; GPS is report-side only."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import hashlib
import json
import numpy as np

from local_pilot_refinement import PilotWorkspace
from sign_aware_pilot import sign_aware_fit,sign_spectrum
from ds23_sign_carrier_prediction import within_frame_carrier_prediction
from ds23_synthetic_precision import make_precision_control
from probe_ds23_sign_carrier_position import OUT,METHODS,context_signed,intervene
from probe_ds23_sign_aware_pilot import OUT as PHASE
from validate_ds23_sign_aware_carrier import OUT as RF
from probe_ds23_frequency_events import cached,summary
from run_ds23_combined_recovery_full import valid,ARMS
from run_algo01_ds23_sample import ROOT,read,write,sha


def replay_RF(job,saved):
    point=job['point'];oid=point['observation_id']
    with np.load(ROOT/job['panel'],allow_pickle=False) as z:
        metadata=json.loads(str(z['metadata_json']));fs=metadata['sample_rate_hz'];v=z[point['window_key']][:,point['receiver_offset']]
    epoch=point['peak']['integer_epoch_sample']+point['peak']['fractional_epoch_offset_samples']
    p=PilotWorkspace(v[:,0].astype(float)+1j*v[:,1].astype(float),fs,point['edge'],epoch)
    base=saved['base_fit'];seed=int(hashlib.sha256(oid.encode()).hexdigest()[:8],16)
    fresh=sign_aware_fit(p,base,seed);f=fresh['fits']['all']
    control=float(sign_spectrum(p,[f['CFO_hz']],f['offset_samples'],f['modulation_ppm'],control=True)['score'][0])
    fresh['checks']['positive_control_margin']=f['score']>control
    fresh['checks']['base_RF_interior']=not any(base.get(k,False) for k in ('frequency_search_boundary','epoch_search_boundary','code_rate_search_boundary'))
    proposal=all(fresh['checks'].values())
    guard=within_frame_carrier_prediction(p,base,fresh)
    differences=[abs(fresh['fits'][s]['CFO_hz']-saved['result']['fits'][s]['CFO_hz']) for s in ('all','even','odd')]
    if max(differences)>1e-6 or proposal!=saved['phase_proposal_accepted'] or (proposal and guard['passed'])!=saved['accepted']:
        raise ValueError('sign-aware RF refit or qualification failed replay')
    return dict(case=saved['case'],observation_id=oid,stratum=saved['stratum'],
        maximum_RF_refit_CFO_difference_hz=max(differences),carrier_accepted=saved['accepted'])


def replay_position(case):
    saved=read(OUT/(case+'.json'))
    if saved['status']!='complete':raise ValueError('real position experiment incomplete')
    scan,node,mask,powers,means,hyper,entries,signed,signed_path=context_signed(case)
    selected=[r for r in read(RF/'evaluation.json')['rows'] if r['case']==case and r['accepted']]
    policies={'incumbent':dict(arms=saved['incumbent_arms'],paired_valid=True,policy_arms=saved['incumbent_arms'])}
    policies.update(saved['results']);rows=[];residuals=[]
    active_ids=set();predictive_ids={o for e in entries for o in e['observation_ids']}
    for method,branch in policies.items():
        changed,overrides,_=intervene(scan,selected,method) if method!='incumbent' else (scan,{}, {})
        pair={}
        for arm,r in branch['arms'].items():
            p=make_precision_control(changed,node,mask,arm,np.asarray(r['phase_reference']),powers,means,hyper,entries,overrides);cached(p)
            x=np.asarray(r['endpoint_east_north_km']);fresh=summary(p,x,entries)
            delta=float(fresh['negative_twice_elbo']-r['negative_twice_elbo'])
            if abs(delta)>1e-6 or fresh['linear_calibration_max_difference']!=0:raise ValueError('position objective or curved-only calibration failed replay')
            for key in ('gates','linear_gates'):
                a=fresh[key]['tracks'] if key=='gates' else fresh[key]
                b=r[key]['tracks'] if key=='gates' else r[key]
                if [(t['component'],t['compatible']) for t in a]!=[(t['component'],t['compatible']) for t in b]:
                    raise ValueError('original position gates changed')
            fresh['final_phase_change_s']=r.get('final_phase_change_s',0.);pair[arm]=fresh
            policy=branch['policy_arms'][arm]
            rows.append(dict(case=case,method=method,arm=arm,paired_valid=branch['paired_valid'],
                trial_latlon=r['endpoint_latlon'],policy_latlon=policy['endpoint_latlon'],RF_objective_replay_difference=delta,
                frequency_RMS_hz=r['RMS_hz'],failed_curved=[t['component'] for t in fresh['gates']['tracks'] if not t['compatible']],
                failed_predictive=[t['component'] for t in fresh['linear_gates'] if not t['compatible']]))
            if method=='incumbent' and arm=='c0':
                for i,sl in zip(p.members,p.slices,strict=True):
                    active_ids.update(o for o,keep in zip(scan.tracks[i]['observation_ids'],mask[sl],strict=True) if keep)
            if case=='DS23-0202' and arm=='fitted_c' and method in ('incumbent','sign_CFO_and_precision'):
                failed={t['component'] for t in saved['results']['sign_CFO_and_precision']['arms'][arm]['gates']['tracks'] if not t['compatible']}
                c=p.calculate(x)
                for i,sl in zip(p.members,p.slices,strict=True):
                    t=p.scan.tracks[i]
                    if t['key'] not in failed:continue
                    use=mask[sl]
                    residuals.append(dict(method=method,component=t['key'],norad=next(r['candidate_norad'] for r in p.rows if r['component']==t['key']),
                        time_s=p.flat_times[sl][use],residual_hz=c['conditional_residual_hz'][sl][use],
                        observation_ids=np.asarray(t['observation_ids'])[use].tolist(),
                        refined=[o in {r['observation_id'] for r in selected} for o in np.asarray(t['observation_ids'])[use]]))
        if valid(pair)!=branch['paired_valid']:raise ValueError('paired original position qualification changed')
        if method!='incumbent':
            expected=branch['arms'] if branch['paired_valid'] else saved['incumbent_arms']
            if branch['policy_arms']!=expected:raise ValueError('fallback policy changed original accepted evidence')
    return dict(rows=rows,residuals=residuals,refined_point_membership=dict(case=case,total=len(selected),
        active_curved=sum(r['observation_id'] in active_ids for r in selected),
        predictive=sum(r['observation_id'] in predictive_ids for r in selected)))


def main():
    position_protocol=read(OUT/'protocol.json');phase_protocol=read(PHASE/'protocol.json')
    for directory in (OUT,PHASE,RF):
        protocol=read(directory/'protocol.json')
        for name,expected in protocol['source_sha256'].items():
            if sha(ROOT/'tools'/name)!=expected:raise ValueError('scientific source changed')
    validation=read(RF/'evaluation.json');lookup={r['observation_id']:r for r in validation['rows']}
    rf_jobs=[j for j in phase_protocol['jobs'] if lookup[j['point']['observation_id']]['phase_proposal_accepted']]
    rf_audit=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(replay_RF,j,lookup[j['point']['observation_id']]) for j in rf_jobs]):rf_audit.append(f.result())
    positions=[replay_position(case) for case in position_protocol['cases']]
    rows=[r for x in positions for r in x['rows']]
    # This is the only import of the evaluation coordinate in this workflow.
    from report_algo02_ds23 import position_error
    for r in rows:
        r['trial_position_error_km']=position_error(r['trial_latlon'])
        r['policy_position_error_km']=position_error(r['policy_latlon'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(13,8))
    methods=['incumbent',*METHODS];colors=['#888888','#5e3c99','#197c91','#c44c31'];labels=['Incumbent','Continuous control','Sign-aware CFO','Sign-aware + precision']
    for k,arm in enumerate(ARMS):
        for m,method in enumerate(methods):
            selected=[next(r for r in rows if (r['case'],r['arm'],r['method'])==(case,arm,method)) for case in position_protocol['cases']]
            x=np.arange(2)+(m-1.5)*.18;values=[r['policy_position_error_km'] for r in selected]
            base=[next(r['policy_position_error_km'] for r in rows if r['case']==s['case'] and r['arm']==arm and r['method']=='incumbent') for s in selected]
            axes[k,0].bar(x,values,width=.17,color=colors[m],label=labels[m])
            axes[k,1].bar(x,1000*(np.asarray(values)-base),width=.17,color=colors[m],label=labels[m])
            for xx,r in zip(x,selected,strict=True):
                if not r['paired_valid']:
                    axes[k,0].plot(xx,r['trial_position_error_km'],'x',color='black',ms=8)
                    axes[k,1].plot(xx,1000*(r['trial_position_error_km']-base[position_protocol['cases'].index(r['case'])]),'x',color='black',ms=8)
        axes[k,0].axhline(.5,ls='--',color='black',lw=.7)
        axes[k,1].axhline(0,color='black',lw=.7)
        for ax in axes[k]:ax.set_xticks(range(2),['DS23-0202','DS23-0274']);ax.grid(axis='y',alpha=.2)
        axes[k,0].set(title=arm,ylabel='Position error (km)')
        axes[k,1].set(title=arm+' · change from incumbent',ylabel='Position error change (m)')
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Four RF-qualified carrier updates · original associations, masks and gates retained\nBlack crosses: rejected trial; filled bars: valid policy with exact incumbent fallback\nSame causal priors and regional cold start; two development scans, not dataset-wide validation')
    fig.tight_layout();fig.savefig(OUT/'position_results.png',dpi=175);plt.close(fig)
    rfrows=[r for r in validation['rows'] if r['phase_proposal_accepted']]
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for r in validation['rows']:
        color='#197c91' if r['accepted'] else '#c44c31' if r['phase_proposal_accepted'] else '0.8'
        axes[0].scatter(r['result']['fits']['all']['coherence_squared'],min(r['result']['heldout_phase_fraction'].values()),s=20,color=color,alpha=.65)
    axes[0].axvline(.8,ls='--',color='black',lw=.7);axes[0].axhline(.9,ls='--',color='black',lw=.7)
    axes[0].set(xlabel='Squared frame-phase coherence',ylabel='Minimum held-out frame phase fraction',title='155 probes: phase evidence alone is insufficient')
    for r in rfrows:
        loss=max(f['heldout_negative_twice_log_likelihood_loss'] for f in r['within_frame_carrier_prediction']['folds'])
        axes[1].scatter(abs(r['CFO_change_from_continuous_hz']),loss,s=50,color='#197c91' if r['accepted'] else '#c44c31')
    axes[1].axhline(9,ls='--',color='black',lw=.7);axes[1].set(yscale='symlog',xlabel='Absolute carrier change from continuous fit (Hz)',ylabel='Maximum held-out within-frame likelihood loss',title='Four apparent corrections fail actual carrier evidence')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('Blue: RF-qualified · red: phase proposal rejected by within-frame carrier test · grey: other rejected probes')
    fig.tight_layout();fig.savefig(OUT/'RF_phase_and_carrier_validation.png',dpi=175);plt.close(fig)
    residuals=[r for x in positions for r in x['residuals']];components=sorted({r['component'] for r in residuals})
    fig,axes=plt.subplots(len(components),2,figsize=(12,3.3*len(components)),squeeze=False)
    for k,component in enumerate(components):
        for j,method in enumerate(('incumbent','sign_CFO_and_precision')):
            r=next(r for r in residuals if r['component']==component and r['method']==method)
            ax=axes[k,j];t=np.asarray(r['time_s']);y=np.asarray(r['residual_hz']);refined=np.asarray(r['refined'])
            ax.plot(t,y,'.-',color='#197c91',lw=.8,ms=4)
            ax.scatter(t[refined],y[refined],s=80,marker='*',color='#c44c31',zorder=3,label='RF-qualified points')
            ax.axhline(0,color='black',lw=.7);ax.grid(alpha=.2)
            ax.set(xlabel='Scan time (s)',ylabel='Conditional residual (Hz)',title=component.split('-RF')[0]+' · '+method)
            if refined.any():ax.legend(fontsize=8)
    fig.suptitle('DS23-0202 · NORAD62496 · assigning5Hz precision makes the original joint residual gates fail\nTrial retained for diagnosis; the accepted policy keeps the original incumbent')
    fig.tight_layout();fig.savefig(OUT/'precision_failure_residuals.png',dpi=175);plt.close(fig)
    audit=dict(position_rows=rows,refined_point_membership=[x['refined_point_membership'] for x in positions],
        RF_proposal_refits=rf_audit,position_endpoint_arm_replays=len(rows),
        maximum_position_RF_objective_replay_difference=max(abs(r['RF_objective_replay_difference']) for r in rows),
        source_result_sha256={c:sha(OUT/(c+'.json')) for c in position_protocol['cases']},
        RF_validation_sha256=sha(RF/'evaluation.json'),protocol_sha256=sha(OUT/'protocol.json'),
        evaluator_sha256=sha(Path(__file__)),GPS_used_only_after_inference_for_reporting=True,
        does_not_establish_dataset_wide_improvement=True)
    write(OUT/'independent_replay_audit.json',audit)
    print('SIGN_CARRIER_REPLAY_COMPLETE',len(rf_audit),'RF proposals and',len(rows),'position endpoint arms',flush=True)
    for r in rows:print(r['case'],r['method'],r['arm'],r['paired_valid'],r['policy_position_error_km'],flush=True)


if __name__=='__main__':main()
