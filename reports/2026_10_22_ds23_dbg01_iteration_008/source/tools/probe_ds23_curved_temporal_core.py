"""Predictive versus actively curved calibration of independently recovered cores."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import run_ds23_dbg01_iteration_008 as runner
import probe_ds23_graph_seeded_paths as parent
from ds23_curved_core_view import curved_core_view
from ds23_predictive_subsets import realize_predictive_subsets
from localize_merged_track_catalogue import raw_curvature
from run_ds23_combined_recovery_full import valid
from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_phase_refreshed import extend_associations
from dbg01_unassociated import ownership
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'curved_temporal_core'


def coverage(d,kind,arm,saved):
    p=parent.build(d,kind,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
    extended=extend_associations(p,x,retained_metrics(p,x));lookup={t['key']:t for t in d['scan'].tracks}
    explicit=[dict(e,compatible=g['compatible']) for e,g in zip(d['entries'],saved['linear_gates'],strict=True)]
    priority=ownership(explicit)
    priority.update(o for i,sl in zip(p.members,p.slices,strict=True)
        for o,use in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if use)
    keys={e['component'] for e in explicit};rows=[];collisions=[]
    for r in extended['tracks']:
        if not r['compatible'] or r['component'] in keys:continue
        row=dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids']))
        if row['association_source']=='frozen_calibration_extension' and set(row['observation_ids'])&priority:
            collisions.append(row['component']);continue
        rows.append(row)
    ids=ownership(rows+explicit);allids={o['observation_id'] for o in d['observations']}
    if not ids<=allids:raise ValueError('derived curved view introduced nonphysical IDs')
    return dict(associated=len(ids),total_GLRT=len(allids),percent=100*len(ids)/len(allids),associated_tracks=len(rows)+len(explicit),
        accepted_observation_ids=sorted(ids),associations=dict(tracks=rows+explicit),colliding_postfit_extensions_omitted=collisions,
        active_curved_points=int(d['keep'].sum()),predictive_points=sum(e['points'] for e in d['entries']))


def offers(d,selected):
    result=[];occupied={o for e in d['entries'] for o in e['observation_ids']}
    for fragment in selected:
        ids=set(fragment['observation_ids'])
        if len(ids)<12 or np.ptp(fragment['times'])<10 or ids&occupied:continue
        for index in d['scan'].curved:
            t=d['scan'].tracks[index];original=t['observation_ids']
            if not ids<set(original) or len(original)-len(ids)!=1:continue
            k=d['base'].members.index(index)
            if d['keep'][d['base'].slices[k]].any():continue
            positions=[i for i,o in enumerate(original) if o in ids]
            if positions!=list(range(1,len(original))) and positions!=list(range(len(original)-1)):continue
            times=np.asarray(t['times']);removed=0 if positions[0]==1 else len(original)-1
            gap=times[1]-times[0] if removed==0 else times[-1]-times[-2]
            z=(times-times.mean())/np.ptp(times);degree=t['pieces'][0]['degree'] if len(t['pieces'])==1 else 0
            if degree<2:continue
            q,_=np.linalg.qr(np.polynomial.legendre.legvander(z,degree));leverage=float(np.sum(q[removed]**2))
            core=dict(t,times=times[positions],values=np.asarray(t['values'])[positions])
            if gap<5*np.median(np.diff(times)) or leverage<.9 or not raw_curvature(core):continue
            result.append(dict(source_index=index,component=t['key'],fragment=fragment,removed_observation_id=original[removed],
                gap_s=float(gap),original_polynomial_endpoint_leverage=leverage,
                core_active_curvature_independently_recomputed=True))
    return sorted(result,key=lambda r:-len(r['fragment']['observation_ids']))[:1]


def one(case):
    runner.configure();d,cov,kind,_=parent.parent(case)
    source=read(parent.OUT/(case+'_persistent5s_selection.json')) if (parent.OUT/(case+'_persistent5s_selection.json')).exists() else dict(selected=[])
    selected=offers(d,source['selected']);write(OUT/(case+'_selection.json'),dict(offers=selected,RF_only_frozen_before_position_fits=True))
    trials=[]
    for offer in selected:
        p=parent.build(d,kind,'c0',d['arms']['c0']['phase_reference']);fragment=offer['fragment']
        changed,entry,receipt=curved_core_view(d,p,fragment,offer['source_index'])
        # Same physical core enters either conditional prediction or the curved
        # likelihood. The original full track and isolated observation stay unused.
        for method in ['core_predictive','core_curved']:
            if method=='core_predictive':
                scan,realized,_=realize_predictive_subsets(d['scan'],[dict(entry,track_index=offer['source_index'],component=offer['component'])])
                dd=dict(d,scan=scan,entries=d['entries']+realized)
            else:dd=changed
            arms={a:parent.refit(dd,kind,a) for a in ['c0','fitted_c']};newcov={a:coverage(dd,kind,a,s) for a,s in arms.items()}
            retained={a:set(cov[a]['accepted_observation_ids'])<=set(newcov[a]['accepted_observation_ids']) for a in arms}
            passed=bool(valid(arms) and all(retained.values()))
            trials.append(dict(method=method,paired_valid=bool(valid(arms)),accepted=passed,arms=arms,coverage=newcov,
                all_parent_accepted_IDs_retained=retained,offer=offer,derived_entry=entry,derived_receipt=receipt,
                independent_curved_core_points=entry['points'],original_likelihood_observations_unchanged=True,
                original_measurements_and_persisted_polynomials_unchanged=True))
            print(case,method,entry['points'],'points, accepted',passed,flush=True)
    write(OUT/(case+'.json'),dict(case=case,trials=trials,diagnostic_prototype_no_default_promotion=True,
        no_GPS_or_following_TLE_used=True))
    return dict(case=case,offers=len(selected),trials=len(trials))


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve curved core hypothesis')
    write(OUT/'protocol.json',dict(cases=read(runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        helper_sha256=sha(Path(curved_core_view.__code__.co_filename)),
        hypothesis='a frozen HMM core with independently active curvature may support calibration after a false graph endpoint join',
        maximum_cores_per_case=1,minimum_core_points=12,minimum_span_s=10,minimum_endpoint_gap_over_median=5,minimum_endpoint_leverage=.9,
        exact_all_but_one_endpoint_of_wholly_unused_original_curved_track=True,
        core_active_curvature_required_not_inherited_from_original_polynomial=True,
        existing_frozen_persistent_HMM_family_and_alias_required=True,
        c0_fitted_c_same_core_and_priors_and_cold5x48_budget=True,
        original_full_source_track_stays_masked_out_and_persisted_contract_unchanged=True,
        no_original_likelihood_measurement_deleted_and_no_cfo_value_changed=True,
        no_GPS_future_TLE_or_new_RF=True,engineering_rule_declared_after_inspecting_original_HMM_core=True,
        same_site_development_only_requires_independent_confirmation_before_release=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,read(OUT/'protocol.json')['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
