"""Qualify simultaneous epoch differences; never insert timing into position.

Common probe start and receiver clock cancel. Satellite transmit clocks and
timing precompensation need not cancel, so geometric range is only a hypothesis.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from probe_ds23_shared_probe_cohort import BULK, OUT as CONFIRMATION
from probe_ds23_sign_carrier_position import context_signed
from ds23_frequency_events import make_event_problem
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import geodetic_to_ecef_km

OUT = ROOT/'reports/2026_10_20_ds23_differential_epoch'
PERIOD = 1/750


def epoch_difference(first, second, sample_rate):
    first, second = np.asarray(first, float), np.asarray(second, float)
    if first.shape != second.shape or first.ndim != 1 or sample_rate <= 0:
        raise ValueError('aligned epoch vectors and positive sampling rate required')
    phase = (second-first)/sample_rate
    return np.unwrap(phase*2*np.pi/PERIOD)*PERIOD/(2*np.pi)


def affine_removed(times, values):
    t, y = np.asarray(times), np.asarray(values)
    design = np.column_stack((np.ones(len(t)), t-t.mean()))
    coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
    return y-design@coefficients, coefficients


def run(case):
    if case in ('DS23-0202', 'DS23-0274'):
        RF = ROOT/'reports/2026_10_20_ds23_same_probe_IQ'
        catalogue = ROOT/'reports/2026_10_20_ds23_differential_catalogue'
        native = ROOT/'reports/2026_10_20_ds23_same_probe_curves'
    else:
        RF, catalogue, native = BULK/'IQ', BULK/'catalogue', BULK/'curves'
    rows = sorted([r for r in read(RF/'evaluation.json')['rows'] if r['case'] == case and r['two_components_qualified']], key=lambda r: r['time_s'])
    jobs = {j['probe']: j for j in read(RF/'protocol.json')['jobs'] if j['case'] == case}
    selected = next(s for s in read(RF/'protocol.json')['selected'] if s['case'] == case)
    fs = next(j['sample_rate_hz'] for j in read(native/'protocol.json')['jobs'] if j['case'] == case and j['lane'] == selected['lane'])
    t = np.array([r['time_s'] for r in rows])
    e1 = [jobs[r['probe']]['first']['epoch']+r['first_fit']['offset_samples'] for r in rows]
    e2 = [jobs[r['probe']]['second']['epoch']+r['second_fit']['offset_samples'] for r in rows]
    observed = epoch_difference(e1, e2, fs)
    nomination = read(catalogue/(case+'.json'))['results']['current_scan_RF_mode']['candidates'][0]
    scan, node, mask, powers, means, hyper, entries, signed, _ = context_signed(case)
    record = signed['policy_arms']['c0']; position = np.asarray(record['endpoint_east_north_km'])
    p = make_event_problem(scan, node, mask, 'c0', np.asarray(record['phase_reference']), powers, means, hyper, [])
    state, c = p.state(position), p.calculate(position)
    observer = geodetic_to_ecef_km(*latlon(position), 0.)
    ranges = []
    for role in ('first', 'second'):
        j = nomination[role+'_index']
        # Use the fitted phase only if the family has original curved support.
        phase = float(state['phases'][j]) if j in p.labels else nomination['phase_'+role+'_s']
        bank = dict(time_s=scan.sky['time_s'], position_km=scan.sky['position_km'][[j]], velocity_km_s=scan.sky['velocity_km_s'][[j]])
        satellite, _ = paired_phase_states(bank, t, np.zeros(len(t), int), np.array([phase]))
        if j in p.supported:
            local = p.labels.index(j); supported = p.supported.index(j)
            indices = np.arange(3*local, 3*local+3)
            modes = dict(time_s=p.mode_bank['time_s'], position_km=p.mode_bank['position_km'][indices], velocity_km_s=p.mode_bank['velocity_km_s'][indices])
            perturbation, _ = paired_phase_states(modes, np.repeat(t, 3), np.tile(np.arange(3), len(t)), np.full(3, phase))
            begin = p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*supported
            satellite += np.einsum('nmc,m->nc', perturbation.reshape(-1, 3, 3), c['coefficient'][begin:begin+3])
        ranges.append(np.linalg.norm(satellite-observer, axis=1))
    expected = (ranges[1]-ranges[0])/299792.458
    data, _ = affine_removed(t, observed); geometry, _ = affine_removed(t, expected)
    residual, clock = affine_removed(t, observed-expected)
    anti, _ = affine_removed(t, observed+expected)
    scale = float(data@geometry/max(geometry@geometry, 1e-30))
    record = dict(case=case, first_norad=nomination['first_norad'], second_norad=nomination['second_norad'],
                  time_s=t, observed_curvature_us=data*1e6, expected_curvature_us=geometry*1e6,
                  residual_us=residual*1e6, observed_to_expected_curvature_scale=scale,
                  expected_curvature_RMS_us=float(np.sqrt(np.mean(geometry**2))*1e6),
                  observed_curvature_RMS_us=float(np.sqrt(np.mean(data**2))*1e6),
                  residual_RMS_us=float(np.sqrt(np.mean(residual**2))*1e6),
                  negative_range_control_RMS_us=float(np.sqrt(np.mean(anti**2))*1e6),
                  differential_clock_rate_ppm=float(clock[1]*1e6), maximum_gap_s=float(np.max(np.diff(t))),
                  largest_predicted_adjacent_delay_change_us=float(np.max(abs(np.diff(expected)))*1e6),
                  no_GPS_used=True, no_new_IQ_read_or_RF=True, timing_not_used_for_position=True,
                  satellite_clock_and_timing_precompensation_not_assumed_absent=True,
                  source_sha256=sha(Path(__file__)), RF_evaluation_sha256=sha(RF/'evaluation.json'))
    write(OUT/(case+'.json'), record)
    return record


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = ['DS23-0202', 'DS23-0274']+read(CONFIRMATION/'selection.json')['cases']
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in cases])]
    write(OUT/'evaluation.json', dict(rows=rows, no_timing_position_fit=True, GPS_used=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for r in rows:
        axes[0].scatter(r['expected_curvature_RMS_us'], r['residual_RMS_us'])
        axes[1].scatter(r['expected_curvature_RMS_us'], r['observed_to_expected_curvature_scale'])
    axes[0].set(xlabel='Expected differential range curvature RMS (us)', ylabel='Observed minus expected, affine removed RMS (us)', title='Simultaneous differential-epoch qualification')
    axes[1].axhline(1, color='k', ls='--', lw=.7)
    axes[1].set(xlabel='Expected differential range curvature RMS (us)', ylabel='Observed / expected curvature scale', title='Physical positive-range hypothesis requires scale near +1')
    for a in axes:
        a.grid(alpha=.2)
    fig.savefig(OUT/'timing_qualification.png', dpi=160); plt.close(fig)
    print('DIFFERENTIAL_TIMING', [(r['case'], round(r['residual_RMS_us'], 3), round(r['observed_to_expected_curvature_scale'], 3)) for r in rows], flush=True)


if __name__ == '__main__':
    main()
