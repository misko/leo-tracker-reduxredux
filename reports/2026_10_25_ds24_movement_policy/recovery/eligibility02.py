"""No-refit correction: protect incumbent families, not dormant nominees."""

import argparse
import copy
from pathlib import Path
import time

import numpy as np

import recovery as r
import repair01 as repair
from ds23_height_problem import geometry_features

OUT = r.HERE/'eligibility02'


def required_modes(parent_supported, original_protected):
    return set(parent_supported)&set(original_protected)


def semantic_columns(p, protected, active_members):
    """Column names survive deletion of unrelated dormant coordinates."""
    nb, ns = p.hardware.shape[1], p.smooth.shape[1]
    columns={f'hardware:{k}':k for k in range(nb)}
    columns.update({f'smooth:{k}':nb+k for k in range(ns)})
    begin=nb+ns
    for j in protected:
        if j not in p.labels:raise ValueError('incumbent phase coordinate disappeared')
        columns[f'phase:{j}']=begin+p.labels.index(j)
        if j in p.supported:
            for k in range(3):columns[f'orbit:{j}:{k}']=begin+len(p.labels)+3*p.supported.index(j)+k
    fragment=begin+len(p.labels)+3*len(p.supported)
    for i in active_members:
        if i not in p.members:raise ValueError('incumbent fragment disappeared')
        columns[f'fragment:{i}']=fragment+p.members.index(i)
    return columns


def design_check(d, trial, arm):
    """Compare semantic nuisance columns at one common fixed RF position."""
    dd=dict(d,node=trial['node'],keep=np.asarray(trial['mask'],bool),means=np.asarray(trial['means']),entries=trial['entries'])
    saved=trial['arms'][arm];reference=np.asarray(saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
    proposed=repair.corrected_build(dd,arm,reference,'support')
    # Match phase references by catalogue identity, not coordinate array index.
    oldref=np.array([reference[proposed.labels.index(j)] if j in proposed.labels else d['all_means'][j]
        for j in d['base'].labels])
    baseline=repair.ORIGINAL_BUILD(d,arm,oldref,'graph')
    original_helper=r.support.build(d,trial['node'],np.asarray(trial['mask'],bool),arm,reference,np.asarray(trial['means']))
    cp,co=proposed.calculate(x),original_helper.calculate(x)
    if proposed.supported!=original_helper.supported or proposed.disabled_new_one_owner_orbit_families!=original_helper.disabled_new_one_owner_orbit_families:
        raise ValueError('original support semantics changed')
    np.testing.assert_allclose(cp['features'],co['features'],rtol=0,atol=0)
    np.testing.assert_allclose(cp['negative_twice_elbo'],saved['negative_twice_elbo'],rtol=1e-8,atol=1e-3)
    protected=set(d['original_protected'])
    required=required_modes(baseline.supported,protected)
    if not required<=set(proposed.supported):raise ValueError('incumbent orbital modes lost')
    active={row['candidate_index'] for row,sl in zip(proposed.rows,proposed.slices,strict=True) if proposed.keep[sl].any()}
    owners={j:{(d['scan'].tracks[i]['receiver'],d['scan'].tracks[i]['channel'])
        for row,i,sl in zip(proposed.rows,proposed.members,proposed.slices,strict=True)
        if row['candidate_index']==j and proposed.keep[sl].any()} for j in active}
    disabled=set(proposed.disabled_new_one_owner_orbit_families)
    if not all(j in active and j not in protected and len(owners[j])==1 for j in disabled):
        raise ValueError('disabled family is not newly active with one owner')
    original_active_members=[i for i,sl in zip(baseline.members,baseline.slices,strict=True) if baseline.keep[sl].any()]
    before=semantic_columns(baseline,protected,original_active_members)
    after=semantic_columns(proposed,protected,original_active_members)
    if set(before)!=set(after):raise ValueError('incumbent nuisance coordinate definition changed')
    # Graph rows are unchanged; preserve original measurement/alias/sigma/power.
    np.testing.assert_array_equal(baseline.values,proposed.values)
    np.testing.assert_array_equal(baseline.q,proposed.q)
    np.testing.assert_array_equal(baseline.point_noise,proposed.point_noise)
    if not np.all(proposed.keep[baseline.keep]):raise ValueError('original mask lost')
    old=geometry_features(baseline,x,0.)['features'];new=geometry_features(proposed,x,0.)['features']
    maximum=0.
    for name in before:
        delta=np.max(np.abs(old[baseline.keep,before[name]]-new[baseline.keep,after[name]]))
        maximum=max(maximum,float(delta))
        np.testing.assert_allclose(old[baseline.keep,before[name]],new[baseline.keep,after[name]],rtol=1e-10,atol=1e-8)
    np.testing.assert_allclose(np.asarray(d['means'])[[baseline.labels.index(j) for j in protected]],
        np.asarray(trial['means'])[[proposed.labels.index(j) for j in protected]],rtol=0,atol=1e-9)
    np.testing.assert_allclose(baseline.phase_sigma,proposed.phase_sigma,rtol=0,atol=0)
    return dict(required_incumbent_modes=sorted(required),disabled_only_new_active_one_owner=sorted(disabled),
        semantic_nuisance_columns=len(before),maximum_original_feature_difference=maximum,
        original_values_aliases_sigmas_RF_and_active_mask_preserved=True,
        original_phase_prior_means_widths_preserved=True,
        original_support_helper_objective_difference=float(cp['negative_twice_elbo']-co['negative_twice_elbo']),
        saved_endpoint_objective_difference=float(cp['negative_twice_elbo']-saved['negative_twice_elbo']))


def freeze():
    repair.verify()
    protocol=dict(revision='eligibility02 no-refit active-incumbent mode guard',
        reason='strict repair01 guard included dormant nominees explicitly permitted to lose newly active one-owner shape modes',
        definition='required modes = parent.supported intersect original_protected',
        apply_to_all_sealed_support_trials_symmetrically=True,no_position_fits=True,no_GPS=True,
        candidate_order_gates_priors_and_ID_requirements_unchanged=True,
        original_protocol_sha256=r.sha(r.HERE/'protocol.json'),
        original_scientific_seal_sha256=r.sha(r.HERE/'scientific_seal.json'),
        support_scientific_seal_sha256=r.sha(repair.OUT/'scientific_seal.json'),
        coordinator_decision_sha256=r.sha(r.HERE.parent/'recovery_eligibility_correction_decision.json'),
        source_sha256={str(p):r.sha(p) for p in [Path(__file__),r.HERE/'test_eligibility02.py']})
    r.write_new(OUT/'protocol.json',protocol)
    r.write_new(OUT/'protocol_seal.json',dict(protocol_sha256=r.sha(OUT/'protocol.json')))


def run():
    repair.verify()
    protocol=r.read(OUT/'protocol.json')
    if r.read(OUT/'protocol_seal.json')['protocol_sha256']!=r.sha(OUT/'protocol.json'):raise ValueError('eligibility protocol changed')
    for name,digest in protocol['source_sha256'].items():
        if r.sha(name)!=digest:raise ValueError('eligibility source changed')
    seal=r.read(repair.OUT/'scientific_seal.json')
    for name,digest in seal['files'].items():
        if r.sha(repair.OUT/name)!=digest:raise ValueError('repaired support result changed')
    rows=[]
    for case in r.CASES:
        d=r.context(case);parent=r.read(r.HERE/case/'parent.json')['coverage']
        source=r.read(repair.OUT/case/'result.json');trials=[]
        for original in source['trials']:
            trial=copy.deepcopy(original)
            checks={arm:design_check(d,trial,arm) for arm in r.ARMS}
            preserved=r.preserve_parent(parent,trial['coverage'],
                {a:required_modes(parent[a]['supported_families'],d['original_protected']) for a in r.ARMS})
            trial.update(strict_original_layout_preservation=original['preservation'],strict_original_layout_accepted=original['accepted'],
                active_incumbent_definition_checks=checks,preservation=preserved,
                accepted=bool(trial['paired_valid'] and r.preserved(preserved)))
            trials.append(trial)
        passing=[t for t in trials if t['accepted']]
        selected=min(passing,key=lambda t:(-t['added_curved_points'],tuple(a['component'] for a in t['additions']))) if passing else None
        result=dict(case=case,status='complete',stage='support_active_incumbent_control',trials=trials,selected=selected,
            policy_arms=selected['arms'] if selected else d['arms'],baseline_fallback=selected is None,
            source_result_sha256=r.sha(repair.OUT/case/'result.json'),no_GPS=True,no_refits=True,
            original_strict_control_remains_separately_reported=True)
        r.write_new(OUT/case/'result.json',result)
        rows.append(dict(case=case,trials=len(trials),passing=len(passing),selected=selected is not None))
    r.write_new(OUT/'execution.json',dict(rows=rows,no_position_fits=True,no_GPS=True,all_terminal=True))
    r.write_new(OUT/'scientific_seal.json',dict(sealed_utc_ns=time.time_ns(),no_GPS_before_seal=True,
        protocol_sha256=r.sha(OUT/'protocol.json'),support_scientific_seal_sha256=r.sha(repair.OUT/'scientific_seal.json'),
        files={str(p.relative_to(OUT)):r.sha(p) for p in sorted(OUT.rglob('*.json')) if p.name!='scientific_seal.json'}))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['freeze','run'])
    globals()[parser.parse_args().stage]()


if __name__=='__main__':main()
