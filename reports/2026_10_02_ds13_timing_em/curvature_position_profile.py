"""Optional satellite curvature screen and bounded, fully profiled site probes.

Research-only: retain original GLRT groups and use the existing finite-set loss.
Never rewrite memberships or production configuration.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT.parent / '2026_10_02_multiscan_localization'),
               str(ROOT.parent / '2026_10_02_localization_benchmark')]


def curvature(times, residual):
    t, y = np.asarray(times, float), np.asarray(residual, float)
    if len(t) < 4 or not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)):
        return dict(status='unassessed', ratio=None)
    x = (t - t.mean()) / 30.
    design = np.column_stack([np.ones(len(t)), x, x*x])
    if np.linalg.matrix_rank(design) != 3:
        return dict(status='unassessed', ratio=None)
    rms = []
    for size in (2, 3):
        d = design[:, :size]
        rms.append(float(np.sqrt(np.mean((y - d @ np.linalg.lstsq(d, y, rcond=None)[0])**2))))
    if rms[1] <= 1e-8:
        return dict(status='unassessed', ratio=None, linear_rms_hz=rms[0], quadratic_rms_hz=rms[1])
    return dict(status='assessed', ratio=rms[0]/rms[1], linear_rms_hz=rms[0], quadratic_rms_hz=rms[1])


def excluded_satellites(tracks, threshold=None):
    if threshold is None:
        return []
    if not np.isfinite(threshold) or threshold < 1:
        raise ValueError('threshold must be finite and >=1')
    return sorted({t['catalog_number'] for t in tracks
                   if t['ratio'] is not None and t['ratio'] > threshold})


def probes(seed=20261003):
    points = [dict(label='roof', east_m=0., north_m=0.)]
    for h in (50., 100.):
        for e, n in ((h, 0), (-h, 0), (0, h), (0, -h)):
            points.append(dict(label=f'E{e:+g}N{n:+g}', east_m=float(e), north_m=float(n)))
    rng = np.random.default_rng(seed)
    for i in range(6):
        angle, radius = rng.uniform(0, 2*np.pi), 500*np.sqrt(rng.uniform())
        points.append(dict(label=f'random-{i+1}', east_m=float(radius*np.sin(angle)),
                           north_m=float(radius*np.cos(angle))))
    return points


def finite_difference(cells, h):
    lookup = {(c['east_m'], c['north_m']): c['objective'] for c in cells}
    origin = lookup[0., 0.]
    gradient = [(lookup[h, 0.] - lookup[-h, 0.])/(2*h),
                (lookup[0., h] - lookup[0., -h])/(2*h)]
    diagonal = [(lookup[h, 0.] + lookup[-h, 0.] - 2*origin)/h**2,
                (lookup[0., h] + lookup[0., -h] - 2*origin)/h**2]
    return dict(step_m=h, gradient_score_per_m=gradient, diagonal_curvature_score_per_m2=diagonal)


def run(output, threshold):
    from all_visible_bank import load_expanded_scan
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from later_tle_comparison import predict
    from finite_set_fit import snapshot_files, assert_snapshot_unchanged
    from position_profile_grid import run_profile, geodesic_position
    from plot_all_glrt_doppler_overlay import serializable
    source = ROOT/'later-tle-timing-aligned-v2/receipt.json'
    receipt = json.loads(source.read_text())
    tle = Path(receipt['latest_snapshot']['path'])
    hashes = snapshot_files([source, tle, Path(__file__), ROOT/'position_profile_grid.py',
                             ROOT/'timing_model.py', ROOT/'rf_calibration_diagnostic.py'])
    assert_snapshot_unchanged(receipt['source_hashes'])
    catalogue = parse_element_sets(tle.read_text())
    lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
    output.mkdir(exist_ok=False)
    def save(name, value):
        (output/name).write_text(json.dumps(serializable(value), indent=2, allow_nan=False)+'\n')
    results = []
    for scan in receipt['scans']:
        label, session = scan['scan'], scan['session']
        print(f'{label}: loading bank and later TLEs', flush=True)
        data = load_expanded_scan(session)
        profile_path = ROOT/'pruned-position-profile-grid'/f'{session}.json'
        profile = json.loads(profile_path.read_text())
        satellites = np.asarray(profile['satellite_indices'], int)
        indices = [lookup[int(n)] for n in data.numbers[satellites]]
        p, v, valid = propagate_candidate_states(catalogue, indices, scan['origin_utc_ns'], data.nodes, np.array([0.]))
        if list(valid) != indices:
            raise ValueError('missing propagated candidates')
        data = copy.copy(data)
        data.position = data.position.copy(); data.velocity = data.velocity.copy()
        data.position[satellites] = p[:, 0]; data.velocity[satellites] = v[:, 0]
        pose_path = Path('/srv/bulk/leo/capture-pose/gauss-r20-lt3d-004b-20261001-v1')/(session+'.json')
        pose = json.loads(pose_path.read_text())['pose_authority']
        lat, lon = pose['latitude_deg'], pose['longitude_deg']
        hashes.update(snapshot_files([profile_path, pose_path]))
        initial = scan['later_fit']
        def fit(selected, position, start):
            vector = None
            attempts = []
            for _ in range(5):
                fitted = run_profile(data, start['parameters'], selected,
                    start['rf_coefficient_hz_per_ghz'], position,
                    probability_override=profile['detection_probability'], start_vector=vector, budget_s=8.)
                vector = fitted['vector']
                attempts.append({k: fitted[k] for k in ('objective','success','status','projected_nuisance_gradient_inf_norm')})
                if fitted['success']:
                    break
            if not fitted['success']:
                raise RuntimeError(f'{label}: unconverged profile: {attempts}')
            fitted['attempts'] = attempts
            return fitted
        roof_position = geodesic_position(lat, lon, 0., 0.)
        roof = fit(satellites, roof_position, initial)
        save(f'{label}-unfiltered-roof.json', roof)
        old_prediction = predict(data, initial['parameters'], satellites, initial['rf_coefficient_hz_per_ghz'])
        roof_prediction = predict(data, roof['parameters'], satellites, roof['rf_coefficient_hz_per_ghz'])
        tracks = []
        for track in (t for t in receipt['tracks'] if t['scan'] == label):
            rows = np.asarray(track['rows'], int)
            column = int(np.flatnonzero(data.numbers[satellites] == track['catalog_number'])[0])
            y = np.asarray(track['later_residual_hz']) + (old_prediction[rows, column]-roof_prediction[rows, column])*11.085e9/data.rf[rows]
            tracks.append(dict(catalog_number=track['catalog_number'], receiver=track['receiver'],
                count=len(rows), span_s=float(np.ptp(track['time_s'])),
                old_reference=curvature(track['time_s'], track['later_residual_hz']),
                **curvature(track['time_s'], y)))
        excluded = excluded_satellites(tracks, threshold)
        print(f'{label}: frozen roof exclusions {excluded}', flush=True)
        save(f'{label}-filter.json', dict(threshold=threshold, excluded=excluded, tracks=tracks))
        variants = {}
        for variant in ('unfiltered', 'filtered'):
            if variant == 'filtered' and not excluded:
                variants[variant] = copy.deepcopy(variants['unfiltered'])
                variants[variant]['identical_to_unfiltered'] = True
                continue
            selected = satellites if variant == 'unfiltered' else np.asarray([s for s in satellites if int(data.numbers[s]) not in excluded])
            if not len(selected):
                raise ValueError('filter excluded every candidate')
            center = roof if variant == 'unfiltered' else fit(selected, roof_position, roof)
            cells = []
            for point in probes():
                e, n = point['east_m'], point['north_m']
                position = geodesic_position(lat, lon, np.degrees(np.arctan2(e, n)), np.hypot(e, n))
                fitted = center if point['label'] == 'roof' else fit(selected, position, center)
                save(f"{label}-{variant}-{point['label']}.json", fitted)
                cell = dict(**point, objective=fitted['objective'], delta_score=fitted['objective']-center['objective'],
                    data_nll=fitted['data_nll'], prior_nll=fitted['nuisance_prior_nll'],
                    success=fitted['success'], nuisance_gradient=fitted['projected_nuisance_gradient_inf_norm'],
                    position_km=position, support=fitted['satellite_support'])
                cells.append(cell)
                print(f"{label} {variant} {point['label']}: delta {cell['delta_score']:+.6f}", flush=True)
            variants[variant] = dict(candidates=data.numbers[selected], cells=cells,
                derivatives=[finite_difference(cells, h) for h in (50., 100.)],
                best=min(cells, key=lambda c: c['objective']))
        results.append(dict(scan=label, session=session, roof_lat_lon=[lat, lon],
                            excluded=excluded, tracks=tracks, variants=variants))
        save('partial.json', results)
    combined = {}
    for variant in ('unfiltered', 'filtered'):
        cells = []
        for i, point in enumerate(probes()):
            values = [r['variants'][variant]['cells'][i] for r in results]
            cells.append(dict(**point, objective=sum(v['objective'] for v in values),
                              delta_score=sum(v['delta_score'] for v in values)))
        combined[variant] = dict(cells=cells, derivatives=[finite_difference(cells,h) for h in (50.,100.)],
                                best=min(cells, key=lambda c:c['objective']))
    assert_snapshot_unchanged(hashes)
    save('receipt.json', dict(results=results, combined=combined, source_hashes=hashes,
        threshold=threshold, random_seed=20261003,
        scope='Original full-group finite-set negative log likelihood + original timing priors; lower better. '
        'Latest archived TLE bank. RX offsets/slopes, common RF coefficient and satellite timing refit at every site. '
        'No mean-motion or polynomial residual correction. Same groups and per-candidate detection probability everywhere. '
        'Curvature computed on frozen final GLRT rows/aliases at unfiltered roof refit; reject satellite across both receivers '
        'within its scan if any assessed ratio strictly exceeds threshold. Unassessed cases retained and flagged. '
        'Screen frozen across sites; excluded candidates removed, not observations. Other candidates can receive soft support. '
        'Filtered/unfiltered absolute scores not directly comparable; use within-variant location differences. '
        'In-sample, local profiled diagnostic, not held-out validation or identity proof. Roof altitude unmeasured; legacy ECEF convention retained.'))
    plot(output, results, combined)


def plot(output, results, combined):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), sharex=True, sharey=True)
    for row, variant in enumerate(('unfiltered', 'filtered')):
        for col, label in enumerate(('A', 'B', 'combined')):
            item = combined[variant] if label == 'combined' else next(r for r in results if r['scan']==label)['variants'][variant]
            cells = item['cells']; ax = axes[row,col]
            delta = np.array([c['delta_score'] for c in cells]); limit = max(abs(delta).max(), 1e-6)
            im = ax.scatter([c['east_m'] for c in cells], [c['north_m'] for c in cells], c=delta,
                            cmap='RdBu_r', vmin=-limit, vmax=limit, s=90, edgecolors='.3')
            for c in cells:
                if c['label'].startswith('random'):
                    ax.annotate(f"{c['delta_score']:+.2f}", (c['east_m'],c['north_m']), xytext=(4,5), textcoords='offset points',fontsize=8)
            ax.plot(0,0,'k+',ms=15,mew=2)
            g = np.asarray(item['derivatives'][0]['gradient_score_per_m']); norm=np.linalg.norm(g)
            if norm:
                ax.arrow(0,0,*(-g/norm*180),width=3,head_width=22,color='black',length_includes_head=True)
            ax.set_title(f"{label} · {variant}\n∂score/∂(E,N) = ({g[0]:+.4f}, {g[1]:+.4f}) / m",fontsize=10)
            ax.set_aspect('equal'); ax.grid(alpha=.2); ax.set_xlim(-550,550);ax.set_ylim(-550,550)
            ax.set_xlabel('East of roof (m)');ax.set_ylabel('North of roof (m)')
            fig.colorbar(im,ax=ax,label='Δ profiled score vs roof')
    fig.suptitle('DS13 · curvature screen and local position score\nAll timing/RX/RF nuisance refitted at each point; lower is better',fontsize=15)
    fig.text(.5,.012,'+ = capture-bound roof. Arrow = local downhill direction (fixed display length). Colors independently scaled.\n'
             'Six seeded-random probes + ±50/100 m cardinal differences. Curvature screen fixed at roof; no polynomial subtraction.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.06,1,.94));fig.savefig(output/'score-gradient.png',dpi=170);plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--curvature-threshold',type=float,default=None,help='Optional; off unless supplied')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    run(args.output,args.curvature_threshold)
