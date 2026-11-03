"""Re-evaluate sealed ALGO04 endpoints; study TLE age without refitting identities.

Run with the recorded modern numerical worktree's Python and PYTHONPATH=src:tools.
Each scan gets its own process because the legacy research loaders bind globals.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds27-algo04-20261031')


def read(path):
    return json.loads(Path(path).read_text())


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=lambda a: a.tolist()) + '\n')


def verified(path, expected):
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if actual != expected.removeprefix('sha256:'):
        raise ValueError('Source hash changed: ' + str(path))
    return read(path)


def age_fields(scan, norad):
    v = scan.elements[str(norad)]['provenance']
    origin, cutoff = scan.receipt['origin_utc_ns'], scan.receipt['cutoff_utc_ns']
    if max(v['element_epoch_utc_ns'], v['collected_utc_ns']) > cutoff:
        raise ValueError('Noncausal source')
    return dict(tle_age_h=(origin-v['element_epoch_utc_ns'])/3.6e12,
                collection_age_h=(origin-v['collected_utc_ns'])/3.6e12,
                epoch_utc_ns=v['element_epoch_utc_ns'],
                collected_utc_ns=v['collected_utc_ns'], origin_utc_ns=origin)


def phase_fields(phase, mean, sigma):
    return dict(phase_s=float(phase), abs_phase_s=float(abs(phase)),
                phase_prior_mean_s=float(mean), phase_prior_sigma_s=float(sigma),
                phase_innovation_s=float(phase-mean),
                abs_phase_innovation_s=float(abs(phase-mean)),
                abs_phase_pull=float(abs(phase-mean)/sigma))


def orbit_fields(coef, metadata):
    if coef is None:
        return {}
    fields = dict(orbital_pull_norm=float(np.linalg.norm(coef)))
    for k, name, scale in [(0, 'mean_motion_rev_day', 'mean_motion_sigma_rev_day'),
                           (1, 'inclination_deg', 'inclination_sigma_deg'),
                           (2, 'raan_deg', 'raan_sigma_deg')]:
        fields[name] = float(coef[k]*metadata[scale])
        fields['abs_'+name] = abs(fields[name])
        fields['prior_'+scale] = float(metadata[scale])
    fields.update(radial_prior_km=metadata['radial_sigma_km'],
                  cross_prior_km=metadata['cross_sigma_km'])
    return fields


def one(z):
    from diagnose_all_large_tracks import context
    from ds23_frequency_events import make_event_problem, attach_event_predictive
    from probe_ds23_frequency_events import cached
    from predictive_new_family import NewFamily
    from debug_fast_graph_unassociated import memberships
    case = z['case']
    terminal = verified(z['terminal_path'], z['terminal_sha256'])
    inv = verified(z['inventory_path'], z['inventory_sha256'])
    proof = terminal['candidate'] if terminal['decision'] == 'ALGO04_additive' else terminal['incumbent']
    selected = proof['selected']
    for path, h in (selected or {}).get('source_receipts', {}).items():
        verified(path, h)
    d = context(inv)
    scan = d['scan']
    rows, receivers, checks, family_inventory = [], [], [], []
    for arm in ('c0', 'fitted_c'):
        p, x = d['problems'][arm]
        additions = []
        if selected:
            if selected['kind'] == 'new_family':
                trial = Path(selected['trial'])
                pr = read(trial/'protocol.json')
                if any(pr.get(k) for k in ('inactive_fragment_sources', 'measurement_refinements', 'graph_bundle_sources')):
                    raise ValueError('Unexpected changed-observation context')
                saved = read(trial/'new_family.json')['arms'][arm]
                additions = [(pr['targets'], pr['family_prior'], saved['family'])]
            elif selected['kind'] == 'joint':
                trial = Path(z['algo04_recovery_path'])/'joint'/('joint-'+arm)
                pr, saved, audit = [read(trial/n) for n in ('protocol.json', 'result.json', 'audit.json')]
                for k, targets in enumerate(pr['targets']):
                    family = NewFamily(scan, targets, d['model'], phase_step=pr['phase_step_s'], allow_uncalibrated_label=True)
                    result = dict(phase_map_s=audit['target']['phases_s'][k],
                                  orbital_posterior_mean=saved['joint_phase_result']['orbital_map_mean'][k],
                                  diagnostics=[q for q in audit['target']['diagnostics'] if q['norad']==targets[0]['norad']])
                    additions.append((targets, family.receipt, result))
            else:
                raise ValueError('Unimplemented selected kind: '+selected['kind'])
            p = make_event_problem(scan, d['node'], d['keep'], arm, np.asarray(saved['phase_reference']),
                                   d['powers'], d['means'], d['model'], [])
            attach_event_predictive(p, d['entries'], d['powers'])
            cached(p)
            x = np.asarray(saved['endpoint_east_north_km'])
            expected = saved['incumbent_objective']
            published = selected['arms'][arm]
        else:
            saved = proof['baseline']['arms'][arm]
            expected = saved['negative_twice_elbo']
            published = saved
        calc, state = p.calculate(x), p.state(x)
        delta = float(calc['negative_twice_elbo']-expected)
        if abs(delta) > 1e-5 or not np.allclose(x, published['endpoint_east_north_km'], atol=1e-9, rtol=0):
            raise ValueError(f'{case} {arm}: endpoint/objective replay mismatch {delta}')
        state_delta = max(float(np.max(abs(np.asarray(state[k])-np.asarray(saved['state'][k])))) for k in ('beta', 'phases', 'smooth'))
        if state_delta > 1e-5:
            raise ValueError(f'State replay mismatch: {state_delta}')
        _, _, ids, owners = memberships(p, x, d['entries'])
        for targets, prior, result in additions:
            for target in targets:
                for oid in target['observation_ids']:
                    if oid in ids:
                        raise ValueError('Duplicated recovered point')
                    ids.add(oid)
                    owners[oid] = target['norad']
        if selected and (ids != set(published['associated_ids']) or owners != published['owners']):
            raise ValueError('Published ownership mismatch')
        counts = Counter(int(n) for n in owners.values())
        base = dict(case=case, arm=arm, decision=terminal['decision'])
        checks.append(dict(base, objective_difference=delta, state_max_difference=state_delta,
                           associated_points=len(ids), selected_endpoint_km=x,
                           baseline_replay_difference=d['replay'][arm],
                           source_terminal_sha256=z['terminal_sha256'], inventory_sha256=z['inventory_sha256']))
        nb, ns = p.hardware.shape[1], p.smooth.shape[1]
        start = nb+ns+len(p.labels)
        active = {r['candidate_index'] for r, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()}
        new_ids = {targets[0]['candidate_index'] for targets, _, _ in additions}
        for n in sorted(counts):
            j = list(scan.norads).index(n)
            role = 'calibration' if j in active else ('new_predictive_family' if j in new_ids else 'predictive_only')
            family_inventory.append(dict(base, norad=n, role=role, associated_points=counts[n], **age_fields(scan,n)))
        for local, j in enumerate(p.labels):
            n = int(scan.norads[j])
            if j not in active or n not in counts:
                continue  # A prior-only/unestimated phase is not a zero correction observation.
            mask = np.zeros(len(p.keep),bool)
            track_bias, track_bias_weights, track_count = [], [], 0
            for k, (r, sl) in enumerate(zip(p.rows, p.slices, strict=True)):
                if r['candidate_index'] == j and p.keep[sl].any():
                    mask[sl] = p.keep[sl]
                    track_count += 1
                    bcol = start+3*len(p.supported)+k
                    track_bias.append(float(np.mean(calc['features'][sl,bcol]*calc['coefficient'][bcol])))
                    track_bias_weights.append(int(p.keep[sl].sum()))
            r = dict(base, norad=n, role='calibration', associated_points=counts[n],
                     calibration_points=int(mask.sum()), calibration_tracks=track_count,
                     rms_hz=float(np.sqrt(np.mean(calc['conditional_residual_hz'][mask]**2))),
                     mean_abs_track_bias_hz=float(np.mean(np.abs(track_bias))),
                     median_elevation_deg=float(np.median(calc['elevation'][mask])),
                     **age_fields(scan,n),
                     **phase_fields(state['phases'][j],d['means'][local],p.phase_sigma[local]))
            if j in p.supported:
                k = p.supported.index(j); sl = slice(start+3*k,start+3*k+3)
                coef = calc['coefficient'][sl]*calc['scales'][2]
                r.update(orbit_fields(coef,p.mode_metadata[j]))
                r['orbit_frequency_rms_hz'] = float(np.sqrt(np.mean((calc['features'][mask,sl]@calc['coefficient'][sl])**2)))
            rows.append(r)
        for targets, prior, result in additions:
            j, n = targets[0]['candidate_index'], targets[0]['norad']
            meta = prior['orbital_prior'].get(str(j),prior['orbital_prior'].get(j))
            diagnostics = result['diagnostics']
            rows.append(dict(base, norad=n, role='new_predictive_family', associated_points=counts[n],
                             calibration_points=0, calibration_tracks=0,
                             rms_hz=float(np.sqrt(np.average([q['profile_RMS_hz']**2 for q in diagnostics],weights=[len(q['times_s']) for q in diagnostics]))),
                             mean_abs_track_bias_hz=float(np.mean([abs(q['profile_bias_hz']) for q in diagnostics])),
                             **age_fields(scan,n),
                             **phase_fields(result['phase_map_s'],prior['phase_prior_mean_s'],prior['phase_prior_sigma_s']),
                             **orbit_fields(np.asarray(result['orbital_posterior_mean']),meta)))
        beta = state['beta']
        rr = dict(base, median_tle_age_h=float(np.median([q['tle_age_h'] for q in rows if q['case']==case and q['arm']==arm])),
                  score=float(published['negative_twice_elbo']), associated_points=len(ids),
                  rms_hz=float(np.sqrt(np.mean(calc['conditional_residual_hz'][p.keep]**2))),
                  c_hz_ghz=float(beta[8]) if arm=='fitted_c' else 0.)
        for g, name in enumerate(('rx1_low','rx1_high','rx2_low','rx2_high')):
            rr[name+'_offset_hz'] = float(beta[g])
            rr[name+'_drift_hz_s'] = float(beta[g+4]/150.)
        rr['rx1_band_offset_hz'] = float(beta[1]-beta[0])
        rr['rx2_band_offset_hz'] = float(beta[3]-beta[2])
        rr['low_rx_offset_hz'] = float(beta[2]-beta[0])
        rr['high_rx_offset_hz'] = float(beta[3]-beta[1])
        rr['smooth_rms_hz'] = float(np.sqrt(np.mean((calc['features'][p.keep,nb:nb+ns]@calc['coefficient'][nb:nb+ns])**2)))
        receivers.append(rr)
    result = dict(case=case,state='complete',families=rows,receivers=receivers,checks=checks,family_inventory=family_inventory)
    write(ROOT/'cases'/(case+'.json'),result)
    print(case, 'replayed',len(rows),'rows',flush=True)
    return dict(case=case,state='complete')


def safe_one(z):
    try:
        return one(z)
    except Exception:
        result = dict(case=z['case'],state='failed',error=traceback.format_exc())
        write(ROOT/'cases'/(z['case']+'.json'),result)
        print(z['case'],result['error'],flush=True)
        return result


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--case'); ap.add_argument('--workers',type=int,default=4)
    args=ap.parse_args(); idx=read(SOURCE/'analysis-index.json')
    cases=[z for z in idx['cases'] if z['state']=='complete' and (not args.case or z['case']==args.case)]
    with ProcessPoolExecutor(max_workers=args.workers,max_tasks_per_child=1) as pool:
        results=list(pool.map(safe_one,cases))
    write(ROOT/'run.json',dict(results=results,unavailable=[z for z in idx['cases'] if z['state']!='complete'],
          scope='Numerical re-evaluation of sealed ALGO04 selected endpoints, not a fresh association search',
          future_TLE=False,GPS_used=False,production_changed=False,age_reference='scan origin minus element epoch',
          source=str(SOURCE),source_index_sha256=hashlib.sha256((SOURCE/'analysis-index.json').read_bytes()).hexdigest()))


if __name__=='__main__':
    main()
