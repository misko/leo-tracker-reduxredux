"""RF-only constrained rescue of failed recovered-curvature trials.

The archived unconstrained trial was cold-started with the same pre-scan causal
catalogue. This experiment refines those RF endpoints, never using site GPS.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from audit_ds23_algo01_coverage import retained_metrics
from ds23_feasible_position import feasible_fit, noise_slacks, residual_slacks
from ds23_predictive_linear import attach_predictive_linear
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_frame_peak_recovery import ARMS, METHODS, augment, context
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import make_problem
from run_algo01_ds23_sample import ROOT, read, write, sha
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.retained_track_likelihood import profile, whitening

SOURCE = ROOT/'reports/2026_10_19_algo03_frame_curved_cohort'
OUT = ROOT/'reports/2026_10_19_algo03_feasible_recovery'


def cached_problem(p):
    calculate = p.calculate
    @lru_cache(maxsize=8)
    def cached(key):
        return calculate(np.asarray(key))
    p.calculate = lambda x: cached(tuple(np.asarray(x, float)))
    return p


def gate_slacks(p, x, entries=()):
    """Every original profile, conditional, alias, elevation and support gate."""
    scan, c, state = p.scan, p.calculate(x), p.state(x)
    frequency, elevation = p.conditional_frequency(x)
    slacks = {}
    owners = {}
    for row, i, sl, alias in zip(p.rows, p.members, p.slices, p.alias, strict=True):
        t, active = scan.tracks[i], p.keep[sl]
        if not active.any():
            continue
        times = t['times'][active]; q = t['rf_hz']/11.5e9
        observed = t['values']-scan.hardware(t, state['beta'])
        observed -= q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        terms = profile(observed[active], q*frequency[sl][active], *whitening(times))
        prefix = t['key']
        values = dict(rms=1-float(terms['rms'][0])/450,
                      bias=1-abs(float(terms['bias'][0]))/3000,
                      alias=.5-abs(int(terms['alias'][0])-alias),
                      elevation=float(elevation[sl][active].min())/10,
                      **noise_slacks(terms['innovations'][0], times))
        slacks.update({prefix+'/profile/'+k:v for k,v in values.items()})
        slacks.update({prefix+'/conditional/'+k:v for k,v in
                       residual_slacks(c['conditional_residual_hz'][sl][active], times).items()})
        owners.setdefault(row['candidate_index'], set()).add((t['receiver'], t['channel']))
    for j in p.supported:
        if j in owners:
            slacks['support/'+str(j)] = float(len(owners[j])-1.5)
    for entry, sl in zip(entries, getattr(p, 'linear_slices', []), strict=True):
        t = scan.tracks[entry['track_index']]
        raw = c['linear_raw_prediction_residual_hz'][sl]
        terms = profile(raw, np.zeros(len(raw)), *scan.white[entry['track_index']], bias_sigma=300.)
        values = dict(rms=1-float(terms['rms'][0])/450,
                      bias=1-abs(float(terms['bias'][0]))/3000,
                      alias=.5-abs(int(terms['alias'][0])),
                      elevation=float(c['linear_elevation'][sl].min())/10,
                      **noise_slacks(terms['innovations'][0], t['times']))
        slacks.update({entry['component']+'/linear/'+k:v for k,v in values.items()})
    return slacks


def linear_metrics(p, x, entries):
    c = p.calculate(x); gates = []
    slacks = gate_slacks(p, x, entries)
    for e in entries:
        values = [v for k,v in slacks.items() if k.startswith(e['component']+'/linear/')]
        gates.append(dict(component=e['component'], compatible=min(values)>=0,
                          points=e['points'], observation_ids=e['observation_ids']))
    return gates


def refit(scan, node, mask, powers, means, model, arm, start, reference, entries=()):
    x = np.asarray(start, float); reference = np.asarray(reference, float); history = []
    for epoch in range(5):
        p = make_problem(scan,node,mask,arm,reference,powers,means,model['multiplier'],model['nu'])
        attach_predictive_linear(p, entries, powers); cached_problem(p)
        def objective(position):
            r = p.residual(position)
            return float(r@r)
        before = gate_slacks(p, x, entries)
        original_pass = all(t['compatible'] for t in retained_metrics(p,x)['tracks'])
        if entries:
            original_pass &= all(t['compatible'] for t in linear_metrics(p,x,entries))
        if original_pass != (min(before.values())>=0):
            raise ValueError('constraint inequalities disagree with original acceptance gates')
        result = feasible_fit(objective, lambda z: list(gate_slacks(p,z,entries).values()),
                              x, p.lower, p.upper, iterations=40)
        x = np.asarray(result['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        history.append(dict(epoch=epoch,fit=result,
                            initial_minimum_gate_slack=min(before.values()),
                            phase_change_s=float(max(abs(phase-reference)))))
        reference = phase
    c = p.calculate(x); curved = p.curved_calculate(x) if entries else c
    slacks = gate_slacks(p, x, entries)
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),state=p.state(x),
                phase_reference=p.reference,history=history,
                final_phase_change_s=history[-1]['phase_change_s'],
                gates=retained_metrics(p,x),linear_gates=linear_metrics(p,x,entries),
                gate_slacks=slacks,minimum_gate_slack=min(slacks.values()),
                active_points=int(mask.sum()),additional_predictive_points=sum(e['points'] for e in entries),
                RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][mask]**2))),
                negative_twice_elbo=c['negative_twice_elbo'],
                curved_negative_twice_elbo=curved['negative_twice_elbo'],
                linear_calibration_max_difference=float(max(abs(c['coefficient']-curved['coefficient']))))


def run(case):
    output = OUT/(case+'.json')
    if output.exists():
        raise FileExistsError('preserve constrained RF hypothesis results')
    selected = read(SOURCE/(case+'_selection.json'))
    previous = read(SOURCE/(case+'_position.json'))
    scan,node,mask,base,old = context(case)
    model=old['hyperparameters_from_pre_RF_TLE_only'];weights=np.asarray(old['weights'])
    _,receipts=phase_widths(scan,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    results={};started=time.monotonic()
    for method in METHODS:
        prev=previous['results'][method]
        if not prev.get('offered_fragments') or prev.get('curved_paired_valid'):
            results[method]=dict(unchanged=True,policy_arms=prev['policy_arms'])
            continue
        fragments=selected['methods'][method]['fragments']
        modified,copied,keep,powers=augment(scan,node,mask,base,weights,fragments)
        starts=prev['curved_gate_steps'][0]['arms']
        pair={arm:refit(modified,copied,keep,powers,means,model,arm,
                       starts[arm]['endpoint_east_north_km'],starts[arm]['phase_reference']) for arm in ARMS}
        valid=pair_passes(pair) and all(v['final_phase_change_s']<=.01 for v in pair.values())
        record=dict(curved_arms=pair,curved_paired_valid=valid,offered_fragments=len(fragments),
                    new_curved_points=sum(len(f['times']) for f in fragments),policy_arms=prev['policy_arms'])
        if valid:
            # Keep the exact previously accepted predictive factors, rather than
            # drop difficult original linear evidence after moving position.
            entries=old['linear_entries'] if old['linear_paired_valid'] else []
            linear={arm:refit(modified,copied,keep,powers,means,model,arm,
                              pair[arm]['endpoint_east_north_km'],pair[arm]['phase_reference'],entries)
                    for arm in ARMS}
            linear_valid=pair_passes(linear,include_linear=True)
            record.update(linear_arms=linear,linear_entries=entries,linear_paired_valid=linear_valid,
                          policy_arms=linear if linear_valid else prev['policy_arms'])
        results[method]=record
        write(OUT/(case+'_partial.json'),dict(case=case,results=results))
        print(case,method,'curved feasible',valid,'policy accepted',record.get('linear_paired_valid',False),flush=True)
    write(output,dict(case=case,results=results,seconds=time.monotonic()-started,
                     original_selection_sha256=sha(SOURCE/(case+'_selection.json')),
                     original_unconstrained_trial_sha256=sha(SOURCE/(case+'_position.json')),
                     no_GPS_position_specific_prior_TLE_change_or_threshold_relaxation=True,
                     original_points_identities_aliases_noise_and_priors_preserved=True,
                     both_c_arms_have_equal_refinement_budgets=True))
    return dict(case=case,seconds=time.monotonic()-started)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    if OUT.exists():
        raise FileExistsError('preserve constrained recovery experiment')
    OUT.mkdir()
    cases=[]
    for path in sorted(SOURCE.glob('*_position.json')):
        previous=read(path)
        if any(r.get('offered_fragments') and not r.get('curved_paired_valid') for r in previous['results'].values()):
            cases.append(previous['case'])
    write(OUT/'protocol.json',dict(cases=cases,selection='all RF-gate-failed offered curved-recovery cases',
          source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_feasible_position.py'),
          source_protocol_sha256=sha(SOURCE/'protocol.json'),workers=args.workers,
          refinement_phase_rounds=5,SLSQP_iterations_per_round=40,
          original_gates_unchanged=True,no_GPS_used_for_selection_or_refinement=True,
          original_valid_linear_evidence_must_be_retained=True,
          paired_c0_fitted_c_inputs_noise_priors_and_budgets_matched=True))
    started=time.monotonic();receipts=[]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for future in as_completed([executor.submit(run,case) for case in cases]):
            result=future.result();receipts.append(result);print(result,flush=True)
    write(OUT/'execution.json',dict(receipts=receipts,seconds=time.monotonic()-started,all_terminal=True))


if __name__=='__main__':
    main()
