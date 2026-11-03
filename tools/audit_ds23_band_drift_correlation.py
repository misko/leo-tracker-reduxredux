"""Independently replay band-drift selection, prior covariance and old gates."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import probe_ds23_band_drift_correlation as inference
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha


def replay(case):
    saved=read(inference.BULK/(case+'.json'))
    if saved['status']!='complete':raise ValueError(f'{case}: band drift experiment not complete')
    context=inference.context_signed(case);signed,source=context[-2:]
    if sha(source)!=saved['source_signed_sha256'] or signed['policy_arms']!=saved['incumbent_arms']:raise ValueError('incumbent changed')
    for actual,expected in [(context[2],saved['mask']),(context[3],saved['powers']),(context[4],saved['means_s'])]:np.testing.assert_array_equal(actual,expected)
    if context[5]!=saved['hyper'] or context[6]!=saved['entries']:raise ValueError('physical priors or linear observation set changed')
    for arm,old in signed['policy_arms'].items():
        null=inference.make(context,arm,np.array(old['phase_reference']),'shared_drift_control')
        r=summary(null,np.array(old['endpoint_east_north_km']),context[6])
        if abs(r['negative_twice_elbo']-old['negative_twice_elbo'])>1e-6:raise ValueError('published incumbent null changed')
    rows=[dict(case=case,method='incumbent',arm=a,policy_latlon=r['endpoint_latlon'],trial_latlon=r['endpoint_latlon'],paired_valid=True,
        frequency_RMS_hz=r['RMS_hz']) for a,r in signed['policy_arms'].items()]
    def endpoint(method,arm,old,linear):
        p=inference.make(context,arm,np.array(old['phase_reference']),method,linear)
        r=summary(p,np.array(old['endpoint_east_north_km']),context[6] if linear else []);delta=r['negative_twice_elbo']-old['negative_twice_elbo']
        if abs(delta)>1e-6 or r['linear_calibration_max_difference']!=0:raise ValueError('band correlation objective or calibration separation fails replay')
        for key in ['gates','linear_gates']:
            a,b=(r[key]['tracks'],old[key]['tracks']) if key=='gates' else (r[key],old[key])
            if [(v['component'],v['compatible']) for v in a]!=[(v['component'],v['compatible']) for v in b]:raise ValueError('original residual gates changed')
        r['final_phase_change_s']=old['final_phase_change_s'];return p,r,delta
    curved={m:endpoint(m,'c0',old,False)[1] for m,old in saved['curved_selection'].items()}
    gain=curved['shared_drift_control']['negative_twice_elbo']-curved['independent_band_drift']['negative_twice_elbo'];c=curved['independent_band_drift']
    choose=bool(gain>2*np.log(2) and c['final_phase_change_s']<=.01 and np.max(abs(c['endpoint_east_north_km']))<=12.5 and all(t['compatible'] for t in c['gates']['tracks']))
    if ('independent_band_drift' if choose else 'incumbent')!=saved['RF_selected_model']:raise ValueError('curved-only covariance selection changed')
    for method,branch in saved['models'].items():
        pair={}
        for arm,old in branch['arms'].items():
            p,r,delta=endpoint(method,arm,old,True);pair[arm]=r
            # Verify physical low/high band slope covariance in native coordinates.
            c1=p.curved_calculate(np.array(old['endpoint_east_north_km'])) if context[6] else p.calculate(np.array(old['endpoint_east_north_km']))
            expected=100.25*np.array([[1.,inference.MODELS[method]],[inference.MODELS[method],1.]])
            for begin in [4,6]:
                prior=c1['coefficient_prior_precision'][[begin,begin+1]]
                design=np.array([[10.,-.5],[10.,.5]])/np.sqrt(prior)
                np.testing.assert_allclose(design@design.T,expected,rtol=1e-12,atol=1e-10)
            rows.append(dict(case=case,method=method,arm=arm,trial_latlon=r['endpoint_latlon'],policy_latlon=branch['policy_arms'][arm]['endpoint_latlon'],
                paired_valid=branch['paired_valid'],frequency_RMS_hz=r['RMS_hz'],objective_replay_difference=delta,
                curved_RF_selection_gain=gain,original_curved_points=r['active_points'],original_predictive_points=r['predictive_points'],
                failed_curved=[v['component'] for v in r['gates']['tracks'] if not v['compatible']],failed_linear=[v['component'] for v in r['linear_gates'] if not v['compatible']]))
        if valid(pair)!=branch['paired_valid'] or branch['policy_arms']!=(branch['arms'] if branch['paired_valid'] else signed['policy_arms']):
            raise ValueError('paired adoption or exact fallback changed')
    expected=saved['models']['independent_band_drift']['policy_arms'] if choose else signed['policy_arms']
    if saved['RF_selected_policy_arms']!=expected:raise ValueError('curvature-selected policy changed')
    for arm in ARMS:
        selected=next(r for r in rows if (r['method'],r['arm'])==('independent_band_drift' if choose else 'incumbent',arm))
        rows.append(dict(selected,method='RF_selected'))
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['development','confirmation'],required=True);args=parser.parse_args()
    protocol=read(inference.OUT/'protocol.json')
    for name,digest in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=digest:raise ValueError('band drift source changed')
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows=[r for f in as_completed([pool.submit(replay,c) for c in protocol[args.stage+'_cases']]) for r in f.result()]
    from report_algo02_ds23 import position_error
    for r in rows:r['position_error_km']=position_error(r['policy_latlon']);r['trial_position_error_km']=position_error(r['trial_latlon'])
    methods=['incumbent',*inference.MODELS,'RF_selected']
    statistics={m:{a:dict(mean_km=float(np.mean([r['position_error_km'] for r in rows if (r['method'],r['arm'])==(m,a)])),
        median_km=float(np.median([r['position_error_km'] for r in rows if (r['method'],r['arm'])==(m,a)])),
        accepted=sum(r['paired_valid'] for r in rows if (r['method'],r['arm'])==(m,a))) for a in ARMS} for m in methods}
    write(inference.OUT/(args.stage+'_independent_replay.json'),dict(rows=rows,statistics=statistics,
        marginal_band_drift_variance_and_original_data_gates_verified=True,linear_calibration_and_covariance_selection_separation_verified=True,
        no_GPS_in_covariance_choice_or_inference=True,same_site_disjoint_scans_not_new_location_validation=True,full_DS23_goal_achieved=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cases=protocol[args.stage+'_cases'];fig,axes=plt.subplots(1,2,figsize=(13,4.8),constrained_layout=True)
    for i,m in enumerate(['incumbent','independent_band_drift','RF_selected']):
        values=[next(r['position_error_km'] for r in rows if (r['case'],r['method'],r['arm'])==(c,m,'fitted_c')) for c in cases]
        axes[0].bar(np.arange(len(cases))+(i-1)*.26,values,width=.25,label=m.replace('_',' '))
        ordered=sorted(values);axes[1].step(ordered,np.arange(1,len(ordered)+1)/len(ordered),where='post',label=m.replace('_',' '))
    axes[0].set(xticks=np.arange(len(cases)),xticklabels=[c[-4:] for c in cases],xlabel='DS23 scan',ylabel='Policy position error (km)')
    axes[1].set(xlabel='Policy position error (km)',ylabel='Empirical cumulative fraction')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Cross-band linear-drift correlation at unchanged per-band prior variance · '+args.stage+'\nOriginal observations/priors/gates, paired c arms; covariance selection uses curved evidence only')
    fig.savefig(inference.OUT/(args.stage+'_position_comparison.png'),dpi=160);plt.close(fig)
    print(args.stage,statistics,flush=True)


if __name__=='__main__':main()
