"""Scientific figures for the gate tradeoff; GPS enters reporting only."""

import copy
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_algo03_frame_peak_recovery import context
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_frequency_events import parameters
from probe_ds23_gate_retention_cohort import OUT, make
from investigate_ds23_0268_remaining_tracks import fine_receiver_basis
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import read, write
from leo.analysis.research.retained_track_likelihood import profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def main():
    case = 'DS23-0114'
    saved = read(OUT / (case + '.json'))
    diagnosis = read(OUT / (case + '_constraint_diagnosis.json'))
    comparison = diagnosis['results']['original_mask']['fitted_c']
    free = comparison['unconstrained']['record']
    constrained = comparison['gate_constrained']['record']
    scan, node, keep, base, old = context(case)
    powers, means, hyper = parameters(scan, base, old)
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    fine = copy.copy(scan)
    fine.rx_basis = [fine_receiver_basis(t['times']) for t in scan.tracks]
    node = copy.deepcopy(node)
    node['seed']['state']['smooth'] = np.zeros((2, fine.rx_basis[0].shape[1]))
    # The failed component is discovered from the RF replay, never selected by error.
    gate = min(comparison['unconstrained']['failed_gates'],
               key=comparison['unconstrained']['failed_gates'].get)
    component = gate.split('/')[0]
    entry_index = next(k for k,e in enumerate(entries) if e['component'] == component)
    track = scan.tracks[entries[entry_index]['track_index']]
    x0, x1 = [np.asarray(r['endpoint_east_north_km']) for r in (free, constrained)]
    samples = []
    for fraction in np.linspace(0, 1, 17):
        x = x0 + fraction * (x1 - x0)
        reference = np.asarray(free['phase_reference'])
        for _ in range(5):
            p = make(fine, node, keep, 'fitted_c', reference, powers, means, hyper, entries)
            reference = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        c = p.calculate(x)
        slacks = gate_slacks(p, x, entries)
        samples.append(dict(distance_km=float(np.linalg.norm(x-x0)),
            negative_twice_elbo=c['negative_twice_elbo'], slope_z=3*(1-slacks[gate])))
    residuals = []
    for name, record in (('RF optimum', free), ('Gate constrained', constrained)):
        p = make(fine, node, keep, 'fitted_c', np.asarray(record['phase_reference']), powers, means, hyper, entries)
        c = p.calculate(np.asarray(record['endpoint_east_north_km']))
        raw = c['linear_raw_prediction_residual_hz'][p.linear_slices[entry_index]]
        terms = profile(raw, np.zeros(len(raw)), *scan.white[entries[entry_index]['track_index']], bias_sigma=300.)
        innovation = terms['innovations'][0]
        noise = batch_noise_screen(innovation[None, :], track['times'])
        residuals.append(dict(name=name, times=track['times'], innovations_hz=innovation,
                              slope_z=float(noise['slope_z'][0]), RMS_hz=float(terms['rms'][0])))
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    ax = axes[0]
    colors = ['#2479aa', '#ba443c', '#444444']
    for name, record, color, marker in (
        ('RF optimum', free, colors[0], 'o'),
        ('Gate constrained', constrained, colors[1], 'X'),
        ('Original ALGO02', saved['baseline_arms']['fitted_c'], colors[2], '^'),
    ):
        x = record['endpoint_east_north_km']
        ax.scatter(*x, color=color, marker=marker, s=75,
                   label=f'{name}: error {position_error(record["endpoint_latlon"]):.2f} km')
    ax.plot([x0[0], x1[0]], [x0[1], x1[1]], color='gray', ls='--')
    ax.set_xlabel('East of regional-box center (km)')
    ax.set_ylabel('North of regional-box center (km)')
    ax.set_title(f'Gate enforcement moves position {np.linalg.norm(x1-x0):.2f} km')
    ax.legend(fontsize=8)
    ax = axes[1]
    distance = [r['distance_km'] for r in samples]
    ax.plot(distance, [r['negative_twice_elbo']-samples[0]['negative_twice_elbo'] for r in samples], color=colors[0])
    ax.set_ylabel('Increase in RF marginal objective', color=colors[0])
    other = ax.twinx()
    other.plot(distance, [r['slope_z'] for r in samples], color=colors[1])
    other.axhline(3, color=colors[1], ls='--', alpha=.6)
    other.set_ylabel('Linear-track slope statistic (gate ≤ 3)', color=colors[1])
    ax.set_xlabel('Distance toward gate-constrained endpoint (km)')
    ax.set_title('Passing the gate sacrifices joint RF fit')
    ax = axes[2]
    for row, color in zip(residuals, colors, strict=False):
        times, residual = np.asarray(row['times']), np.asarray(row['innovations_hz'])
        ax.scatter(times, residual, s=23, color=color, alpha=.8,
                   label=f'{row["name"]}: slope z={row["slope_z"]:.2f}')
        ax.plot(times, np.polyval(np.polyfit(times-times.mean(), residual, 1), times-times.mean()), color=color)
    ax.axhline(0, color='gray', lw=.8)
    ax.set_xlabel('Time in scan (s)')
    ax.set_ylabel('Profile residual innovation (Hz)')
    ax.set_title(f'RX{track["receiver"]} CH{track["channel"]} · {len(track["times"])} linear samples')
    ax.legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=.15)
    fig.suptitle('DS23-0114 · fitted c · same observations, identities, aliases and priors\n'
                 'A marginal residual-slope failure can bias a fully gate-constrained position', fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .90))
    fig.savefig(OUT / 'DS23-0114_gate_tradeoff.png', dpi=180, bbox_inches='tight')
    plt.close(fig)
    write(OUT / 'DS23-0114_gate_tradeoff.json', dict(component=component, path=samples,
        residuals=residuals, reporting_errors_km={
            name:position_error(record['endpoint_latlon'])
            for name,record in [('RF optimum',free), ('Gate constrained',constrained)]},
        GPS_used_only_for_reported_errors=True, no_position_or_association_fit_uses_GPS=True))


if __name__ == '__main__':
    main()
