"""Saved-endpoint audit; no new identity/position selection or evaluation GPS."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, '/srv/bulk/leo/research/ds24-bottlenecks-20261024/information')
import diagnose_information as info
import algo02_scan as algo
from ds23_height_problem import geometry_features
from probe_ds23_graph_seeded_paths import build

HERE = Path(__file__).resolve().parent
ROOTS = {g: Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')/g
         for g in ('ch1_4', 'ch5_8')}
ROOTS['all'] = Path('/srv/bulk/leo/research/ds25-20261024')


def one(job):
    group, case = job
    root = ROOTS[group]
    source = root/'family_cavity/position'/f'{case}.json'
    saved = json.loads(source.read_text())
    algo.bind_run_directory(root)
    selected = saved['selected'] if saved['accepted'] else None
    d = dict(scan=algo.load_scan(root, case),
             node=selected['node'] if selected else saved['baseline_node'],
             keep=np.asarray(saved['original_mask'], bool), powers=np.asarray(saved['powers']),
             model=saved['model'], means=np.asarray(selected['means'] if selected else saved['baseline_means']),
             entries=selected['entries'] if selected else saved['baseline_entries'])
    records = {}
    for arm, s in saved['policy_arms'].items():
        p = build(d, 'default', arm, s['phase_reference'])
        x = np.asarray(s['endpoint_east_north_km'])
        c = p.calculate(x)
        delta = float(c['negative_twice_elbo']-s['negative_twice_elbo'])
        assert abs(delta) < 1e-3, (group, case, arm, delta)
        coefficient = c['coefficient'].copy()
        def prediction(xy):
            geometry = geometry_features(p, xy, 0.)
            return p.q*geometry['intercept']+geometry['features']@coefficient
        def derivative(step):
            return np.column_stack([(prediction(x+v)-prediction(x-v))/(2*step)
                                    for v in np.eye(2)*step])[p.keep]
        j = derivative(.02)
        rel = np.linalg.norm(j-derivative(.04))/np.linalg.norm(j)
        assert rel < 1e-5
        g = p.noise_groups[p.keep]
        w = d['powers'][g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u = c['features'][p.keep]
        prior = c['coefficient_prior_precision']
        rx, ch, family = info.row_metadata(p)
        groups, names = info.column_groups(p, 0), info.column_names(p, [])
        information = info.summarize_design(j, u, w, prior, rx[p.keep], ch[p.keep],
                                           family[p.keep], groups, names, audit=True)
        latent = c['latent_coefficient']
        prior_cost = {name: float(np.sum(prior[ix]*latent[ix]**2)) for name, ix in groups.items()}
        begin = p.hardware.shape[1]+p.smooth.shape[1]
        rows = []
        for k, label in enumerate(p.labels):
            mask = family[p.keep] == label
            if not mask.any():
                continue
            keep_members = [i for i, sl in zip(p.members, p.slices, strict=True)
                            if p.keep[sl].any() and p.rows[p.members.index(i)]['candidate_index'] == label]
            tracks = [p.scan.tracks[i] for i in keep_members]
            ix = begin+k
            phase = coefficient[ix]*p.phase_sigma[k]
            rows.append(dict(norad=int(p.scan.norads[label]), curved_points=int(mask.sum()),
                             receivers=sorted({int(t['receiver']) for t in tracks}),
                             channels=sorted({int(t['channel']) for t in tracks}),
                             t_min=min(float(min(t['times'])) for t in tracks),
                             t_max=max(float(max(t['times'])) for t in tracks),
                             phase_s=phase, prior_mean_s=d['means'][k], phase_sigma_s=p.phase_sigma[k],
                             standardized_phase_from_prior=(phase-d['means'][k])/p.phase_sigma[k],
                             latent_phase_precision=prior[ix],
                             phase_prior_quadratic=prior[ix]*latent[ix]**2,
                             conditional_gradient_fixed_nuisance=-2*j[mask].T@(w[mask]*c['conditional_residual_hz'][p.keep][mask])))
        objective = lambda pos: float(p.calculate(pos)['negative_twice_elbo'])
        h = info.hessian(objective, x, .1)
        gradient = [(objective(x+v)-objective(x-v))/.02 for v in np.eye(2)*.01]
        records[arm] = dict(replay_objective_delta=delta, derivative_step_relative_change=rel,
                            endpoint_east_north_km=x, curved=information, prior_quadratic=prior_cost,
                            families=rows, objective_gradient_at_saved_endpoint=gradient,
                            objective_half_hessian=h, state=p.state(x),
                            active_points=int(p.keep.sum()), predictive_points=sum(e['points'] for e in d['entries']))
    out = dict(group=group, case=case, source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
               arms=records, no_GPS_used=True, fixed_saved_identities_and_observations=True,
               no_position_refit=True, conditional_information_not_calibrated_uncertainty=True)
    info.write(HERE/f'{group}_{case}.json', out)
    print(group, case, {a: r['curved']['all']['principal_sigma_km'][0] for a, r in records.items()}, flush=True)
    return dict(group=group, case=case)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    jobs = [(g, c) for g in ROOTS for c in ('DS24-0015', 'DS24-0019')]
    info.write(HERE/'protocol.json', dict(jobs=jobs, arms=['c0', 'fitted_c'], saved_objective_tolerance=1e-3,
               cases_selected_for_largest_paired_error_gaps_only_not_for_parameter_tuning=True,
               no_GPS_in_calculation=True, no_new_fit=True))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(one, jobs))
    info.write(HERE/'execution.json', dict(complete=True, jobs=rows))
