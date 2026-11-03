"""Independent endpoint replay and report-only accuracy for reception trials."""

import numpy as np
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import summary
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_reception_identity_position import OUT,BULK
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import read,write,sha
from localize_merged_track_catalogue import distance_km


def main():
    protocol=read(OUT/'protocol.json');rows=[]
    for offer in protocol['offers']:
        case=offer['case'];path=BULK/(case+'.json');saved=read(path)
        if saved['status']!='complete':raise ValueError('terminal complete position trial required')
        scan,node,mask,powers,means,hyper,entries,signed,binding=context_signed(case)
        if sha(binding)!=saved['signed_incumbent_sha256']:raise ValueError('incumbent binding changed')
        replay={};details={}
        for arm in ARMS:
            before=saved['incumbent_arms'][arm];after=saved['arms'][arm];x=np.array(after['endpoint_east_north_km'])
            p=make_event_problem(scan,saved['candidate_node'],mask,arm,np.array(after['phase_reference']),powers,np.array(saved['new_means_s']),hyper,[])
            attach_event_predictive(p,saved['candidate_entries'],powers)
            calculated=summary(p,x,saved['candidate_entries'])
            difference=calculated['negative_twice_elbo']-after['negative_twice_elbo']
            if abs(difference)>1e-6:raise ValueError('candidate endpoint RF likelihood changed')
            np.testing.assert_allclose(calculated['state']['phases'],after['state']['phases'],atol=1e-8,rtol=0)
            assert [r['compatible'] for r in calculated['gates']['tracks']]==[r['compatible'] for r in after['gates']['tracks']]
            old_ids={o for r in before['gates']['tracks']+before.get('linear_gates',[]) for o in r['observation_ids']}
            new_ids={o for r in calculated['gates']['tracks']+calculated.get('linear_gates',[]) for o in r['observation_ids']}
            if old_ids!=new_ids:raise ValueError('original position observations changed')
            # Geographic truth enters only here, after the independent RF replay.
            reference=(37.849061591561885,-122.48574968092912)
            details[arm]=dict(incumbent_error_km=distance_km(before['endpoint_latlon'],reference),
                rejected_trial_error_km=distance_km(after['endpoint_latlon'],reference),
                incumbent_RMS_hz=before['RMS_hz'],trial_RMS_hz=after['RMS_hz'],
                original_observations=len(old_ids),failed_curved_tracks=sum(not r['compatible'] for r in calculated['gates']['tracks']),
                failed_predictive_tracks=sum(not r['compatible'] for r in calculated.get('linear_gates',[])),
                same_original_observation_ids_verified=True,objective_replay_difference=difference,
                **saved['score_details'][arm])
            replay[arm]=dict(calculated,final_phase_change_s=after['final_phase_change_s'])
        if valid(replay)!=saved['paired_valid']:raise ValueError('paired gates changed on independent replay')
        if not saved['accepted'] and saved['policy_arms']!=saved['incumbent_arms']:raise ValueError('exact fallback changed')
        rows.append(dict(case=case,original_norad=offer['block']['original_norad'],candidate_norad=offer['candidate']['norad'],
            accepted=saved['accepted'],paired_valid=saved['paired_valid'],arms=details,source_sha256=sha(path)))
    write(OUT/'independent_replay_audit.json',dict(rows=rows,all_endpoints_and_original_ids_replayed=True,
        accepted_cases=sum(r['accepted'] for r in rows),no_position_improvement_adopted=True,
        five_RF_selected_engineering_cases_not_full_DS23_generalization=True,report_only_GPS=True))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
    x=np.arange(len(rows));w=.32
    axes[0].bar(x-w/2,[r['arms']['fitted_c']['incumbent_error_km'] for r in rows],w,label='Retained incumbent')
    axes[0].bar(x+w/2,[r['arms']['fitted_c']['rejected_trial_error_km'] for r in rows],w,color='#c95b56',label='Rejected identity trial')
    axes[0].set(xticks=x,xticklabels=[r['case'][-4:] for r in rows],ylabel='Position error (km), report only',xlabel='DS23 scan')
    axes[0].legend();axes[0].grid(axis='y',alpha=.2)
    axes[1].bar(x,[r['arms']['fitted_c']['frequency_bound_gain'] for r in rows],color='#c95b56')
    axes[1].axhline(0,color='black',lw=.8)
    axes[1].set(xticks=x,xticklabels=[r['case'][-4:] for r in rows],ylabel='Full frequency-bound gain\npositive favors challenger',xlabel='DS23 scan')
    axes[1].grid(axis='y',alpha=.2)
    fig.suptitle('Closest reception-screen identities: all five fail unchanged paired gates\nMatched c=0/fitted-c replays recorded; plot shows fitted-c; no change adopted')
    fig.savefig(OUT/'reception_identity_position_checks.png',dpi=150);plt.close(fig)
    print('Replayed',len(rows),'cases,',2*len(rows),'candidate endpoints; adopted',sum(r['accepted'] for r in rows),flush=True)


if __name__=='__main__':main()
