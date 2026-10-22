"""Bounded predictive subset test after an independent whole-versus-clutter audit."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import run_ds23_dbg01_iteration_007 as runner
import probe_ds23_new_family_prediction as model
from ds23_predictive_subsets import realize_predictive_subsets,assert_realized_predictive_membership
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'endpoint_predictive_view'


def choose(diagnostic):
    result=[]
    for row in diagnostic['rows']:
        choices={a:{r['candidate_index']:r for r in rs if r['eligible']} for a,rs in row['arms'].items()}
        common=set(choices['c0'])&set(choices['fitted_c'])
        if not common:continue
        j=max(common,key=lambda j:min(choices[a][j]['penalized_gain'] for a in choices))
        a,b=choices['c0'][j],choices['fitted_c'][j]
        if a['alias']!=b['alias']:continue
        result.append(dict(offer=row['offer'],candidate_index=j,norad=a['norad'],alias=a['alias'],
            minimum_penalized_gain=min(a['penalized_gain'],b['penalized_gain'])))
    return sorted(result,key=lambda r:-r['minimum_penalized_gain'])[:2]


def one(case):
    d=runner.engine.current_setup(case);parent=read(runner.RAW/'new_family_prediction_v2'/(case+'.json'))['trials']['physical_prior']
    diagnostic=read(runner.RAW/'endpoint_group_diagnostic'/(case+'.json'));selected=choose(diagnostic)
    write(OUT/(case+'_selection.json'),dict(selected=selected,RF_only_selection_frozen_before_position_fit=True,
        original_point_values_and_polynomials_unchanged=True,unselected_endpoint_remains_unassociated_not_deleted=True))
    if not parent['paired_valid'] or not selected:
        write(OUT/(case+'.json'),dict(case=case,changed=False,accepted=False,reason='no qualifying predictive endpoint model or invalid parent'))
        return dict(case=case,changed=False)
    subsets=[];quarantined=[]
    for choice in selected:
        offer=choice['offer'];t=d['scan'].tracks[offer['track_index']];ids=np.asarray(t['observation_ids'])[offer['indices']].tolist()
        quarantined.append(t['observation_ids'][offer['removed_index']])
        subsets.append(dict(track_index=offer['track_index'],component=t['key'],candidate_index=choice['candidate_index'],norad=choice['norad'],
            alias=choice['alias'],points=len(ids),observation_ids=ids,association_source='independently_predicted_endpoint_core'))
    scan,realized,receipts=realize_predictive_subsets(d['scan'],subsets)
    assert_realized_predictive_membership(scan,realized,quarantined)
    if scan.curved!=d['scan'].curved:raise ValueError('predictive core must not enter calibration')
    for old,new in zip(d['scan'].tracks,scan.tracks,strict=False):
        if not np.array_equal(old['values'],new['values']):raise ValueError('original CFO values changed')
    entries=parent['entries']+realized;dd=dict(d,scan=scan)
    arms={a:model.refit(dd,a,entries,True) for a in ['c0','fitted_c']}
    passed=bool(valid(arms) and all(np.max(abs(np.asarray(r['new_family_phases_s'])))<=15.000001 for r in arms.values()))
    write(OUT/(case+'.json'),dict(case=case,changed=True,accepted=passed,arms=arms,entries=entries,
        predictive_subset_receipts=receipts,quarantined_observation_ids=quarantined,
        additional_points=sum(e['points'] for e in realized),original_curved_calibration_unchanged=True,
        diagnostic_only_development_extension_not_in_full_population_method=True))
    return dict(case=case,changed=True,accepted=passed,extra_points=sum(e['points'] for e in realized))


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    record=dict(cases=read(runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        source_diagnostic_protocol_sha256=sha(runner.RAW/'endpoint_group_diagnostic/protocol.json'),
        maximum_cores=2,no_additional_search_or_residual_point_trimming=True,
        predictive_only_calibration_unchanged=True,original_GLRT_denominator_and_persisted_contracts_unchanged=True,
        no_GPS_or_following_TLE_used=True,paired_c_arms_same_subsets_aliases_priors_and_five48_budget=True,
        not_in_frozen_random20_or_full_DS23_method=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve predictive-view trial')
    write(OUT/'protocol.json',record)
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,record['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,RF_selection_complete_before_geographic_scoring=True))


if __name__=='__main__':main()
