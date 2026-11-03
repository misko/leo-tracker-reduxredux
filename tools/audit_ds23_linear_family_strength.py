"""Rebuild linear-family variance and original gates before position reporting."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import probe_ds23_linear_family_strength as inference
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha


def replay(case):
    saved=read(inference.BULK/(case+'.json'))
    if saved['status']!='complete':raise ValueError(f'{case}: incomplete position experiment')
    context=inference.context_signed(case);signed,source=context[-2:]
    if sha(source)!=saved['source_signed_sha256'] or signed['policy_arms']!=saved['incumbent_arms']:raise ValueError('incumbent changed')
    for actual,expected in [(context[2],saved['mask']),(context[3],saved['powers']),(context[4],saved['means_s'])]:np.testing.assert_array_equal(actual,expected)
    if context[5]!=saved['hyper'] or context[6]!=saved['entries']:raise ValueError('predictive observations or other priors changed')
    rows=[dict(case=case,method='incumbent',arm=arm,trial_latlon=r['endpoint_latlon'],policy_latlon=r['endpoint_latlon'],paired_valid=True,
               frequency_RMS_hz=r['RMS_hz']) for arm,r in signed['policy_arms'].items()]
    # Reconstruct the fixed rule directly, separately from the inference helper.
    supported={}
    base=inference.make(context,'c0',np.zeros(len(context[4])),'unit_control')
    for row,sl,power in zip(base.rows,base.slices,context[3],strict=True):
        if context[2][sl].any():supported[row['candidate_index']]=max(supported.get(row['candidate_index'],0.),power)
    expected_strength=np.array([supported[e['candidate_index']] for e in context[6]])
    for method,record in saved['models'].items():
        pair={}
        for arm,old in record['arms'].items():
            p=inference.make(context,arm,np.array(old['phase_reference']),method);x=np.array(old['endpoint_east_north_km']);r=summary(p,x,context[6])
            delta=r['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(delta)>1e-6 or r['linear_calibration_max_difference']!=0:raise ValueError('prediction or fixed calibration failed replay')
            strength=np.ones(len(context[6])) if method=='unit_control' else expected_strength
            np.testing.assert_array_equal(getattr(p,'linear_family_strength',np.array([])),strength)
            if context[6]:
                from ds23_predictive_linear import linear_geometry
                _,_,sigma,group,_=linear_geometry(p,context[6]);np.testing.assert_array_equal(p.calculate(x)['linear_predictive_sigma_hz'],sigma*np.sqrt(2/strength[group]))
            for key in ['gates','linear_gates']:
                a,b=(r[key]['tracks'],old[key]['tracks']) if key=='gates' else (r[key],old[key])
                if [(v['component'],v['compatible']) for v in a]!=[(v['component'],v['compatible']) for v in b]:raise ValueError('original residual gates changed')
            r['final_phase_change_s']=old['final_phase_change_s'];pair[arm]=r
            rows.append(dict(case=case,method=method,arm=arm,trial_latlon=r['endpoint_latlon'],policy_latlon=record['policy_arms'][arm]['endpoint_latlon'],
                paired_valid=record['paired_valid'],frequency_RMS_hz=r['RMS_hz'],objective_replay_difference=delta,
                original_curved_points=r['active_points'],original_predictive_points=r['predictive_points'],
                family_strength=strength,failed_curved=[v['component'] for v in r['gates']['tracks'] if not v['compatible']],
                failed_linear=[v['component'] for v in r['linear_gates'] if not v['compatible']]))
        if valid(pair)!=record['paired_valid'] or record['policy_arms']!=(record['arms'] if record['paired_valid'] else signed['policy_arms']):
            raise ValueError('paired gate decision or exact fallback changed')
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['development','confirmation'],required=True);args=parser.parse_args()
    protocol=read(inference.OUT/'protocol.json')
    for name,digest in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=digest:raise ValueError('family-strength scientific source changed')
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows=[r for f in as_completed([pool.submit(replay,c) for c in protocol[args.stage+'_cases']]) for r in f.result()]
    from report_algo02_ds23 import position_error
    for row in rows:row['position_error_km']=position_error(row['policy_latlon']);row['trial_position_error_km']=position_error(row['trial_latlon'])
    statistics={method:{arm:dict(mean_km=float(np.mean([r['position_error_km'] for r in rows if (r['method'],r['arm'])==(method,arm)])),
        median_km=float(np.median([r['position_error_km'] for r in rows if (r['method'],r['arm'])==(method,arm)])),
        accepted=sum(r['paired_valid'] for r in rows if (r['method'],r['arm'])==(method,arm))) for arm in ARMS} for method in ['incumbent']+inference.MODELS}
    write(inference.OUT/(args.stage+'_independent_replay.json'),dict(rows=rows,statistics=statistics,
        original_observations_labels_priors_and_gates_preserved=True,linear_calibration_unchanged=True,
        no_GPS_in_variance_rule_or_inference=True,objectives_across_different_noise_models_not_compared=True,
        same_site_disjoint_scans_not_new_location_validation=True,full_DS23_goal_achieved=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cases=protocol[args.stage+'_cases'];fig,axes=plt.subplots(1,2,figsize=(13,4.8),constrained_layout=True)
    for i,method in enumerate(['incumbent']+inference.MODELS):
        values=[next(r['position_error_km'] for r in rows if (r['case'],r['method'],r['arm'])==(c,method,'fitted_c')) for c in cases]
        axes[0].bar(np.arange(len(cases))+(i-1)*.26,values,width=.25,label=method.replace('_',' '))
        ordered=sorted(values);axes[1].step(ordered,np.arange(1,len(ordered)+1)/len(ordered),where='post',label=method.replace('_',' '))
    axes[0].set(xticks=np.arange(len(cases)),xticklabels=[c[-4:] for c in cases],xlabel='DS23 scan',ylabel='Policy position error (km)')
    axes[1].set(xlabel='Policy position error (km)',ylabel='Empirical cumulative fraction')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Linear prediction with fixed curved-family support variance · '+args.stage+'\nShared curved covariance, every measurement and all original gates retained; fitted c shown')
    fig.savefig(inference.OUT/(args.stage+'_position_comparison.png'),dpi=160);plt.close(fig)
    print(args.stage,statistics,flush=True)


if __name__=='__main__':main()
