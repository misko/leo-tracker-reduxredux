"""Replay truth-conditioned controls and verify their forward coordinate map."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from ds23_synthetic_known_nuisance import conditional_prior, known_problem, attach_known_predictive, COMPONENTS, generating_linear_bias
from probe_ds23_frequency_events import summary, cached
from probe_ds23_synthetic_known_nuisance import OUT, SOURCE, VARIANTS, setup
from run_ds23_combined_recovery_full import ARMS
from run_algo01_ds23_sample import ROOT, read, write, sha


def audit_case(case, site):
    scan, node, mask, powers, means, hyper, entries, truth, baseline = setup(case, site)
    # Recreate the per-physical-ID Gaussian draw independently of perturb_tracks.
    members = {e['track_index'] for e in entries}
    p = known_problem(scan, node, mask, 'c0', np.asarray(truth['true_phases_s']), powers, means, hyper, truth, COMPONENTS)
    members.update(p.members)
    ids = sorted({oid for i in members for oid in scan.tracks[i]['observation_ids']})
    meta = scan.fixed_window_noise
    noise = np.random.default_rng(194729 + int(case.split('-')[1])).normal(size=len(ids))
    scales = [meta['per_observation_noise_sigma_hz'][o] if meta['extra_parameter_BIC_gain'] > 0 else scan.radio_sigma_hz for o in ids]
    by_id = dict(zip(ids, noise * scales, strict=True))
    forward = []
    for arm in ARMS:
        p = known_problem(scan, node, mask, arm, np.asarray(truth['true_phases_s']), powers, means, hyper, truth, COMPONENTS)
        mean, _, _ = conditional_prior(truth['coordinate_widths'], p.fitted_c, means, p.phase_sigma, truth, COMPONENTS)
        geometry = geometry_features(p, site, 0.)
        raw = p.values - p.q * geometry['intercept'] - geometry['features'] @ mean
        expected = np.array([by_id[o] for i in p.members for o in scan.tracks[i]['observation_ids']])
        maximum = float(np.max(abs(raw - expected)))
        if maximum > 1e-6: raise ValueError('truth-conditioned curved mean does not match generator')
        linear_maximum = 0.
        if entries:
            view, values, _, groups, _ = linear_geometry(p, entries)
            geometry = geometry_features(view, site, 0.)
            raw = values - view.q * geometry['intercept'] - geometry['features'] @ mean - generating_linear_bias(truth, len(entries))[groups]
            expected = np.array([by_id[o] for e in entries for o in scan.tracks[e['track_index']]['observation_ids']])
            linear_maximum = float(np.max(abs(raw - expected)))
            if linear_maximum > 1e-6: raise ValueError('truth-conditioned predictive mean does not match generator')
        forward.append(dict(arm=arm, curved_maximum_forward_difference_hz=maximum, predictive_maximum_forward_difference_hz=linear_maximum))
    rows = []
    for variant, known in VARIANTS.items():
        path = OUT / (case + '_' + variant + '.json'); saved = read(path)
        if saved['status'] != 'complete': raise ValueError('incomplete truth-conditioned fit')
        for arm in ARMS:
            r = saved['arms'][arm]
            p = known_problem(scan, node, mask, arm, np.asarray(r['phase_reference']), powers, means, hyper, truth, known)
            attach_known_predictive(p, entries, powers, truth, known); cached(p)
            fresh = summary(p, np.asarray(r['endpoint_east_north_km']), entries)
            delta = float(fresh['negative_twice_elbo'] - r['negative_twice_elbo'])
            if abs(delta) > 1e-6 or fresh['linear_calibration_max_difference'] != 0:
                raise ValueError('RF replay or calibration isolation failed')
            for key in ('gates', 'linear_gates'):
                a = fresh[key]['tracks'] if key == 'gates' else fresh[key]
                b = r[key]['tracks'] if key == 'gates' else r[key]
                if [(t['component'], t['compatible']) for t in a] != [(t['component'], t['compatible']) for t in b]:
                    raise ValueError('original gate replay differs')
            rows.append(dict(case=case, variant=variant, arm=arm, error_km=r['synthetic_position_error_km'],
                RF_objective_replay_difference=delta, saved_result_sha256=sha(path)))
    return dict(case=case, forward_mean_checks=forward, rows=rows)


def main():
    protocol = read(OUT / 'protocol.json'); evaluation = read(OUT / 'evaluation.json')
    if not evaluation['complete'] or evaluation['protocol_sha256'] != sha(OUT / 'protocol.json'):
        raise ValueError('incomplete or changed oracle protocol')
    for name, expected in protocol['source_sha256'].items():
        if sha(ROOT / 'tools' / name) != expected: raise ValueError('truth-conditioned implementation changed')
    audits = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(audit_case, c, protocol['site_by_case'][c]) for c in protocol['cases']]):
            audits.append(f.result())
    rows = [r for a in audits for r in a['rows']]
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    variants = ['baseline', *VARIANTS]
    labels = ['Original\nuncertainty', 'Known RX\noffsets/drift', 'Known RX\nsmooth', 'Known\nphase', 'Known orbit\nshape', 'Known\nfragment bias', 'Known phase\nand smooth', 'All nuisance\nknown']
    fig, axes = plt.subplots(1, 2, figsize=(17, 6), sharey=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        for k, variant in enumerate(variants):
            if variant == 'baseline':
                errors = [read(SOURCE / (c + '_draw0_all.json'))['arms'][arm]['synthetic_position_error_km'] for c in protocol['cases']]
            else:
                errors = [r['error_km'] for r in rows if r['variant'] == variant and r['arm'] == arm]
            ax.scatter(k + np.linspace(-.12, .12, len(errors)), errors, s=18, alpha=.7, color='#197c91')
            ax.plot([k-.22, k+.22], [np.median(errors)]*2, color='#c44c31', lw=2)
            ax.scatter([k], [np.mean(errors)], marker='D', s=30, color='#5e3c99', zorder=4)
        ax.axhline(.5, color='black', ls='--', lw=.8)
        ax.set(xticks=range(len(variants)), xticklabels=labels, yscale='log', ylabel='Synthetic position error (km)', title=arm)
        ax.tick_params(axis='x', labelsize=8); ax.grid(alpha=.2)
    fig.suptitle('Diagnostic value of known corrections · same 20 templates, observations and noise\nTrue corrections supplied by simulator; not an operational algorithm or real-data accuracy gain\nRed bars: medians · purple diamonds: means · cold start: regional centre')
    fig.tight_layout(); fig.savefig(OUT / 'known_nuisance_error_distributions.png', dpi=175); plt.close(fig)
    write(OUT / 'independent_replay_audit.json', dict(cases=audits,
        replayed_instance_arms=len(rows), maximum_RF_replay_difference=max(abs(r['RF_objective_replay_difference']) for r in rows),
        protocol_sha256=sha(OUT / 'protocol.json'), evaluation_sha256=sha(OUT / 'evaluation.json'),
        audit_source_sha256=sha(Path(__file__)), real_DS23_accuracy_gain=False))
    print('KNOWN_NUISANCE_AUDIT_COMPLETE', len(rows), 'endpoint replays and', len(audits)*2, 'forward-mean checks', flush=True)


if __name__ == '__main__': main()
