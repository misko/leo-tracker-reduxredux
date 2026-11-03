"""Independent matched-c replay; geographic truth is report-only."""

import numpy as np
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import summary
from probe_ds23_sign_carrier_position import context_signed,SIGNED_AUDIT
from probe_ds23_cross_RX_curves_position import OUT,BULK,augment,INVENTORY
from inventory_ds23_cross_RX_curves import SOURCE
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha
from localize_merged_track_catalogue import distance_km


def main():
    execution=read(OUT/'execution.json')
    if execution['failures']:raise ValueError('all position trials must finish before evaluation')
    inventory=read(INVENTORY/'inventory.json');lookup={r['case']:r for r in inventory['rows']}
    bindings=read(SIGNED_AUDIT)['evidence'];rows=[]
    for source in sorted(inventory['rows'],key=lambda r:r['case']):
        case=source['case'];path=BULK/(case+'.json');details={}
        if source['fragments']:
            saved=read(path);scan,node,mask,powers,means,hyper,entries,signed,binding=context_signed(case)
            changed,newnode,newmask,newpowers,added=augment(scan,node,mask,powers,means,hyper,signed,source)
            old_flat=make_event_problem(scan,node,mask,'c0',np.zeros(len(means)),powers,means,hyper,[])
            original_ids=[o for i,sl in zip(old_flat.members,old_flat.slices,strict=True) for o,keep in zip(scan.tracks[i]['observation_ids'],mask[sl],strict=True) if keep]
            original_ids.extend(o for e in entries for o in e['observation_ids'])
            target_ids=original_ids+[o for e in added for o in e['observation_ids']]
            if len(set(target_ids))!=len(target_ids):raise ValueError('duplicate physical observation is active')
            replay={}
            for arm in ARMS:
                record=saved['arms'][arm];x=np.array(record['endpoint_east_north_km'])
                p=make_event_problem(changed,newnode,newmask,arm,np.array(record['phase_reference']),newpowers,means,hyper,[])
                attach_event_predictive(p,entries,newpowers)
                calculated=summary(p,x,entries);delta=calculated['negative_twice_elbo']-record['negative_twice_elbo']
                if abs(delta)>1e-6:raise ValueError('opposite RX endpoint likelihood changed')
                np.testing.assert_allclose(calculated['state']['phases'],record['state']['phases'],atol=1e-8,rtol=0)
                assert [r['compatible'] for r in calculated['gates']['tracks']]==[r['compatible'] for r in record['gates']['tracks']]
                actual={o for r in calculated['gates']['tracks']+calculated.get('linear_gates',[]) for o in r['observation_ids']}
                if actual!=set(target_ids):raise ValueError('endpoint does not preserve exactly old plus distinct new observations')
                replay[arm]=dict(calculated,final_phase_change_s=record['final_phase_change_s'])
                details[arm]=dict(objective_replay_difference=delta,failed_curved_tracks=sum(not r['compatible'] for r in calculated['gates']['tracks']),
                    original_observations=len(original_ids),added_observations=len(target_ids)-len(original_ids),
                    old_RMS_hz=saved['incumbent_arms'][arm]['RMS_hz'],trial_RMS_hz=record['RMS_hz'])
            if valid(replay)!=saved['accepted']:raise ValueError('acceptance changed on independent replay')
            if not saved['accepted'] and saved['policy_arms']!=saved['incumbent_arms']:raise ValueError('exact failed-pair fallback changed')
            old=saved['incumbent_arms'];chosen=saved['policy_arms'];accepted=saved['accepted']
        else:
            binding=ROOT/bindings[case]['path']
            if sha(binding)!=bindings[case]['sha256']:raise ValueError('no-offer signed incumbent binding changed')
            signed=read(binding);old=chosen=signed['policy_arms'];accepted=False
        # Reporting begins after inference and replay. No truth enters a choice.
        for arm in ARMS:
            truth=(37.849061591561885,-122.48574968092912)
            details.setdefault(arm,{})
            details[arm].update(incumbent_error_km=distance_km(old[arm]['endpoint_latlon'],truth),
                policy_error_km=distance_km(chosen[arm]['endpoint_latlon'],truth))
        rows.append(dict(case=case,offered=bool(source['fragments']),accepted=accepted,arms=details,
            original_points_added=source['qualifying_original_points'] if accepted else 0,
            all_points_added=source['qualifying_curved_points'] if accepted else 0))
    statistics={}
    for stratum,subset in [('all_scans',rows),('offered_scans',[r for r in rows if r['offered']])]:
        statistics[stratum]={}
        for arm in ARMS:
            before=np.array([r['arms'][arm]['incumbent_error_km'] for r in subset]);after=np.array([r['arms'][arm]['policy_error_km'] for r in subset])
            statistics[stratum][arm]=dict(count=len(subset),incumbent_mean_km=float(np.mean(before)),incumbent_median_km=float(np.median(before)),
                policy_mean_km=float(np.mean(after)),policy_median_km=float(np.median(after)),
                improved_scans=int(np.sum(after<before-1e-9)),worsened_scans=int(np.sum(after>before+1e-9)))
    write(OUT/'independent_replay_audit.json',dict(rows=rows,statistics=statistics,
        replayed_endpoints=2*sum(r['offered'] for r in rows),accepted_cases=sum(r['accepted'] for r in rows),
        original_points_recovered=sum(r['original_points_added'] for r in rows),total_distinct_points_added=sum(r['all_points_added'] for r in rows),
        exact_original_evidence_plus_distinct_added_native_points_verified=True,
        all_original_gates_unchanged_and_replayed=True,same_site_no_new_location_validation=True,
        no_GPS_inference_or_new_RF_collection=True,full_DS23_half_km_goal_achieved=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(13,4.8),constrained_layout=True)
    offered=[r for r in rows if r['offered']];x=np.arange(len(offered))
    for arm,color in [('c0','#3b729b'),('fitted_c','#b94850')]:
        axes[0].plot(x,[1000*(r['arms'][arm]['policy_error_km']-r['arms'][arm]['incumbent_error_km']) for r in offered],'.-',label=arm,color=color)
    axes[0].axhline(0,color='black',lw=.8)
    axes[0].set(xticks=x,xticklabels=[r['case'][-4:] for r in offered],ylabel='Position error change (m)\nnegative improves',xlabel='DS23 scan')
    axes[0].tick_params(axis='x',rotation=60);axes[0].legend();axes[0].grid(alpha=.2)
    axes[1].bar(x,[r['all_points_added'] for r in offered],color='#467c9f',label='All distinct points')
    axes[1].bar(x,[r['original_points_added'] for r in offered],color='#8fbeab',label='Original winners recovered')
    axes[1].set(xticks=x,xticklabels=[r['case'][-4:] for r in offered],ylabel='Points retained after both-arm gates',xlabel='DS23 scan')
    axes[1].tick_params(axis='x',rotation=60);axes[1].legend()
    fig.suptitle(f'Opposite-RX curved evidence: matched position and coverage effects\n{len(rows)} scans; no point trimming, no GPS inference; no promotion')
    fig.savefig(OUT/'cross_RX_curve_position_comparison.png',dpi=150);plt.close(fig)
    print(statistics,flush=True)


if __name__=='__main__':main()
