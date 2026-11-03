"""Finite satellite/unknown-family MAP search with every original factor scored."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import combinations
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_unknown_polynomial import make_unknown_problem, unknown_ledger, unobserved_student_gap
from ds23_frequency_events import make_event_problem, attach_event_predictive
from investigate_dsx01_localization_failures import fit
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import cached, summary
from probe_ds23_symmetric_family_selection import SIGNED
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_unknown_polynomial'
ARMS = ('c0','fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),
        ROOT/'tools/ds23_unknown_polynomial.py',ROOT/'tools/dsx01_hierarchical_bound.py',
        ROOT/'tools/ds23_frequency_events.py')}


def prepare():
    OUT.mkdir(exist_ok=True); path=OUT/'protocol.json'
    if path.exists():
        p=read(path)
        if p['source_sha256']!=hashes():
            raise ValueError('frozen satellite/unknown experiment changed')
        return p
    cohort=read(ROOT/'reports/2026_10_20_ds23_excluded_catalogue/calibration_protocol.json')
    p=dict(development_cases=cohort['development_cases'],confirmation_cases=cohort['confirmation_cases'],
        pilot_cases=cohort['pilot_cases'],source_sha256=hashes(),workers=24,
        incumbent='published signed-prior policy, with original fallbacks',
        hypothesis='forcing every retained family to be a named satellite can bias position even when a polynomial is convincing',
        original_observations_all_scored=True,
        polynomial='independent observed-CFO process per original fragment; degree mixture 1..4 with probabilities .5,.25,.125,.125',
        polynomial_basis='fixed (time_s-150)/150; zero-mean Gaussian coefficients with SD pilot_period*[4,4,2,1,1]',
        curved_unknown_noise='same original point noise, Gamma(2,2), original fractional power',
        predictive_unknown_noise='same original point noise times sqrt(2), unit Gaussian likelihood power',
        alias_measure='both hypotheses conditional on the same original unwrapped alias branch; no wrapped/conditional comparison',
        discrete_prior='independent family unknown probability .05, truncated to at most two unknowns; common normalization cancels',
        unobserved_independent_Student_priors_collapsed_exactly=True,
        screen='all eligible single unknown families at incumbent c0 position; five fixed-position phase rounds; top six singles nominate all pair combinations',
        fits='top four singles and top two pairs under full-observation coded score; same six hypotheses in both c arms; minimum four known families and 80 curved points',
        position_start_km=[0,0],box_width_km=25,phase_rounds=5,position_iterations=48,
        null='matched cold all-known refit AND normalized saved-incumbent endpoint replay',
        adoption='original known curved/predictive gates; active physical phases bounded +/-15 and true reference difference<=.01; both c-arm coded gains >2log2 versus better valid saved/cold null; lowest c0 cost',
        policy_fallback='exact published signed incumbent; no scan removed',
        unknown_observations_not_counted_satellite_associated=True,
        no_unknown_or_linear_observation_updates_receiver_calibration=True,
        no_new_RF_future_TLE_GPS_location_prior_or_satellite_whitelist=True,
        cohort_reused_not_untouched_locations=True,
        primary='fitted-c mean AND median improve in both 20-scan cohorts; disclose matched c0 and cold-null controls',
        goal_population=413)
    write(path,p);return p


def factory(scan,node,keep,arm,reference,powers,means,model,entries,unknown,ledger):
    return cached(make_unknown_problem(scan,node,keep,arm,reference,powers,means,model,entries,unknown,ledger))


def active_change(p,x):
    phase=p.state(x)['phases'][p.labels]
    use=p.active_phase_local
    change=float(np.max(abs(phase[use]-p.reference[use])))
    bounded=bool(np.max(abs(phase[use]))<=15)
    return np.clip(phase,-15,15),change,bounded


def endpoint(p,x,history):
    phase,change,bounded=active_change(p,x)
    record=summary(p,x,p.known_entries)
    record.update(history=history,final_phase_change_s=change,active_phases_bounded=bounded,
        unknown_families=p.unknown_families,unknown_points=sum(r['points'] for r in p.unknown_rows),
        all_original_scored_points=p.original_position_points,original_observation_count_preserved=True)
    return record


def refit(scan,node,keep,arm,powers,means,model,entries,unknown,ledger):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for epoch in range(5):
        p=factory(scan,node,keep,arm,reference,powers,means,model,entries,unknown,ledger)
        fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
        phase,change,bounded=active_change(p,x)
        history.append(dict(epoch=epoch,fit=fitted,phase_change_s=change));reference=phase
    return endpoint(p,x,history)


def pair_valid(arms):
    return bool(pair_passes(arms,include_linear=True) and
        all(r['active_phases_bounded'] and r['final_phase_change_s']<=.01 for r in arms.values()))


def run(case):
    prepare();directory=OUT/case;directory.mkdir(exist_ok=True)
    path=directory/'result.json'
    if path.exists():
        return dict(case=case,cached=True)
    began=time.monotonic()
    scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    active_labels=set(np.asarray(base.labels)[base.flat_labels][keep])
    if {e['candidate_index'] for e in entries}-active_labels:
        raise ValueError('predictive-only family needs an explicitly marginalized prior model')
    incumbent=signed['policy_arms'];ledger=unknown_ledger(base,keep,entries,powers)
    original_ids=sorted(oid for rows in ledger.values() for r in rows for oid in r['observation_ids'])
    if len(original_ids)!=int(keep.sum())+sum(e['points'] for e in entries):
        raise ValueError('unknown ledger misses original position observations')
    for item in scan.elements.values():
        provenance=item['provenance']
        if max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])>scan.receipt['cutoff_utc_ns']:
            raise ValueError('future element in original catalogue')
    old_replays=[];normalized={}
    for arm in ARMS:
        r=incumbent[arm];x=np.asarray(r['endpoint_east_north_km']);reference=np.asarray(r['phase_reference'])
        p=make_event_problem(scan,node,keep,arm,reference,powers,means,model,[])
        attach_event_predictive(p,entries,powers)
        before=p.calculate(x)
        if abs(before['negative_twice_elbo']-r['negative_twice_elbo'])>1e-3:
            raise ValueError('published endpoint does not replay')
        collapsed=factory(scan,node,keep,arm,reference,powers,means,model,entries,[],ledger)
        after=collapsed.calculate(x)
        inactive=len(p.labels)-len(np.unique(p.flat_labels[keep]))
        expected=inactive*unobserved_student_gap(model['nu'])
        delta=before['negative_twice_elbo']-after['negative_twice_elbo']
        np.testing.assert_allclose(before['coefficient'],after['coefficient'],atol=1e-8,rtol=1e-9)
        if abs(delta-expected)>1e-5:
            raise ValueError('collapsed null changed more than unobserved prior normalization')
        normalized[arm]=after['negative_twice_elbo']
        old_replays.append(dict(arm=arm,old_RF_difference=before['negative_twice_elbo']-r['negative_twice_elbo'],
            unobserved_phases=inactive,prior_collapse_cost_difference=delta,expected_gap=expected))
    labels=np.asarray(base.labels)[base.flat_labels];families=np.unique(labels[keep]).tolist()
    def eligible(unknown):
        physical=keep & ~np.isin(labels,unknown)
        return len(np.unique(labels[physical]))>=4 and int(physical.sum())>=80
    x=np.asarray(incumbent['c0']['endpoint_east_north_km'])
    def screen(unknown):
        reference=np.asarray(incumbent['c0']['phase_reference'])
        for _ in range(5):
            p=factory(scan,node,keep,'c0',reference,powers,means,model,entries,unknown,ledger)
            reference,change,bounded=active_change(p,x)
        return dict(unknown_families=unknown,cost=p.calculate(x)['negative_twice_elbo'],
            active_phase_change_s=change,active_phases_bounded=bounded)
    singles=sorted([screen([j]) for j in families if eligible([j])],key=lambda r:(r['cost'],r['unknown_families']))
    top=[r['unknown_families'][0] for r in singles[:6]]
    pairs=sorted([screen(sorted(pair)) for pair in combinations(top,2) if eligible(pair)],
                 key=lambda r:(r['cost'],r['unknown_families']))
    nominees=[r['unknown_families'] for r in singles[:4]+pairs[:2]]
    write(directory/'screen.json',dict(case=case,singles=singles,pairs=pairs,nominees=nominees,
        ledger={str(k):v for k,v in ledger.items()},normalized_incumbent_costs=normalized,
        incumbent_replays=old_replays,original_position_observation_ids=original_ids,
        original_mask=keep,incumbent_binding=binding,no_GPS_used=True))
    trials=[]
    for unknown in [[]]+nominees:
        pair={arm:refit(scan,node,keep,arm,powers,means,model,entries,unknown,ledger) for arm in ARMS}
        trial=dict(unknown_families=unknown,arms=pair,paired_valid=pair_valid(pair))
        trials.append(trial)
        write(directory/('trial_'+('none' if not unknown else '_'.join(map(str,unknown)))+'.json'),trial)
    cold=trials[0]
    reference={arm:min(normalized[arm],cold['arms'][arm]['negative_twice_elbo']) if cold['paired_valid'] else normalized[arm]
               for arm in ARMS}
    eligible_trials=[]
    for trial in trials[1:]:
        gains={arm:reference[arm]-trial['arms'][arm]['negative_twice_elbo'] for arm in ARMS}
        trial['coded_gains']=gains
        if trial['paired_valid'] and min(gains.values())>2*np.log(2):
            eligible_trials.append(trial)
    winner=min(eligible_trials,key=lambda r:r['arms']['c0']['negative_twice_elbo']) if eligible_trials else None
    write(path,dict(case=case,trials=trials,accepted=winner is not None,
        norad_by_label={str(j):int(scan.norads[j]) for j in base.labels},
        selected_unknown_families=winner['unknown_families'] if winner else [],
        policy_arms=winner['arms'] if winner else incumbent,incumbent_arms=incumbent,
        cold_null=cold,normalized_incumbent_costs=normalized,reference_costs=reference,
        original_mask=keep,incumbent_binding=binding,source_sha256=hashes(),
        screen_sha256=sha(directory/'screen.json'),original_position_observation_ids=original_ids,
        no_GPS_future_TLE_new_RF_or_original_observation_omission=True,seconds=time.monotonic()-began))
    row=dict(case=case,accepted=winner is not None,unknown=winner['unknown_families'] if winner else [],
             fitted_hypotheses=len(trials),seconds=time.monotonic()-began)
    print(row,flush=True)
    return row


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('prepare','pilot','cohort'),required=True)
    stage=parser.parse_args().stage;p=prepare()
    if stage!='prepare':
        if stage=='cohort' and not read(OUT/'pilot_verification.json')['qualified']:
            raise ValueError('independent pilot verification required before full cohort')
        cases=p['pilot_cases'] if stage=='pilot' else p['development_cases']+p['confirmation_cases']
        receipts=[]
        with ProcessPoolExecutor(max_workers=min(24,len(cases))) as pool:
            futures={pool.submit(run,c):c for c in cases}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(stage+'_progress.json'),dict(completed=len(receipts),total=len(cases)))
        errors=[r for r in receipts if 'error' in r]
        write(OUT/(stage+'_execution.json'),dict(all_terminal=True,receipts=receipts,errors=errors))
        print('Terminal',len(receipts),'errors',errors,flush=True)
