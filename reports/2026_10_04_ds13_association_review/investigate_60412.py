"""Frozen-membership residual and nominal pointing audit; no reassignment or new fit."""
import json
import sys
from pathlib import Path

import numpy as np

from association_audit import (digest, dump, interpolate_positions, polynomial_audit,
                               sky_geometry, write_csv)

HERE = Path(__file__).resolve().parent
OUT = HERE / 'satellite-60412'
BULK = Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
ALIAS = 1 / 4.4e-6
COLORS = {1: '#0072b2', 2: '#e69f00', 3: '#009e73', 4: '#cc79a7'}


def diagnostic_prediction(t, y, ch, degree):
    """Channel intercepts plus shared time polynomial; same nested OLS as audit."""
    u = (t - t.mean()) / max(float(np.ptp(t)), 1.)
    design = np.column_stack([ch == c for c in np.unique(ch)] +
                             [u ** k for k in range(1, degree + 1)])
    return design @ np.linalg.lstsq(design, y, rcond=None)[0]


def main():
    OUT.mkdir(exist_ok=True)
    evidence = json.loads((HERE / 'orientation-evidence.json').read_text())
    full = np.load(HERE / 'A-assigned-observations.npz')
    mask = full['satellite'] == 60412
    d = {k: full[k][mask] for k in full.files}
    assert len(d['row_id']) == 240
    assert not np.any(np.load(HERE / 'B-assigned-observations.npz')['satellite'] == 60412)
    sources = [Path(__file__), HERE / 'association_audit.py',
               HERE / 'A-assigned-observations.npz', HERE / 'B-assigned-observations.npz',
               HERE / 'orientation-evidence.json', BULK / 'position-top-2km/A-profile-input.npz',
               BULK / 'profile_top_2km.py']
    residuals = {'saved': {'fitted-c': d['fitted_c_residual_hz'], 'zero-c': d['zero_c_residual_hz']},
                 'roof': {}}
    sys.path.insert(0, str(BULK))
    from profile_top_2km import Engine
    geometry, comparisons, timing = {}, {}, {}
    for arm in ('fitted-c', 'zero-c'):
        path = HERE / f'gradient-by-satellite/A-{arm}.json'
        sources.append(path)
        record = json.loads(path.read_text())
        engine = Engine('A', arm)
        x = np.asarray(record['roof_fit']['vector'])
        from joint_inputs import _coordinates
        np.testing.assert_allclose(_coordinates(x[:2]), evidence['operator_roof_lat_lon'], atol=1e-9, rtol=0)
        engine.obj.base.deadline = float('inf')
        prediction, visible, _ = engine.obj.base.predict(x[:engine.obj.size], with_jacobian=True)
        prediction += (engine.obj.features @ x[engine.obj.size:])[:, None]
        lookup = {int(r): i for i, r in enumerate(engine.data.original_rows)}
        rows = np.array([lookup[int(r)] for r in d['row_id']])
        np.testing.assert_allclose(engine.data.times[rows], d['time_s'], atol=1e-10)
        index = int(np.flatnonzero(engine.data.numbers == 60412)[0])
        errors = (engine.data.measured[:, None] - prediction + ALIAS / 2) % ALIAS - ALIAS / 2
        residuals['roof'][arm] = errors[rows, index]
        shifts = engine.obj.base.state(x[:engine.obj.size])['total_shifts_s']
        timing[arm] = float(shifts[index])
        positions = interpolate_positions(engine.data.nodes, engine.data.position[index],
                                          d['time_s'] + shifts[index])
        geometry[arm] = sky_geometry(positions, *evidence['operator_roof_lat_lon'],
                                     d['rx'], evidence['nominal_axes_enu'])
        assert np.all(visible[rows, index])
        alternatives = np.where(visible[rows], abs(errors[rows]), np.inf)
        alternatives[:, index] = np.inf
        best = alternatives.argmin(axis=1)
        other = alternatives[np.arange(len(rows)), best]
        d[f'roof_{arm}_nearest_other_id'] = engine.data.numbers[best]
        d[f'roof_{arm}_nearest_other_abs_hz'] = other
        for rx in (0, 1):
            m = d['rx'] == rx
            comparisons[f'{arm}-RX{rx}'] = dict(
                n=int(m.sum()), nearest_selected_alternative_within_600=int(np.sum(other[m] <= 600)),
                nearest_selected_alternative_better=int(np.sum(other[m] < abs(errors[rows[m], index]))),
                median_nearest_alternative_abs_hz=float(np.median(other[m])),
                candidate_count=len(engine.data.numbers),
                scope='Other selected IDs at their saved global roof-fit timings, not exhaustive or individually refitted identity alternatives.')
        d[f'roof_{arm}_residual_hz'] = residuals['roof'][arm]
    metrics = []
    for model, arms in residuals.items():
        for arm, error in arms.items():
            for rx in (0, 1):
                m = d['rx'] == rx
                for ch in [0] + sorted(set(d['channel'][m])):
                    q = m if ch == 0 else m & (d['channel'] == ch)
                    for controlled in (False, True) if ch == 0 else (False,):
                        metrics.append(dict(model=model, arm=arm, rx=rx, channel=int(ch),
                            channel_controlled=controlled, span_s=float(np.ptp(d['time_s'][q])),
                            **polynomial_audit(d['time_s'][q], error[q], d['channel'][q], controlled)))
    write_csv(OUT / 'residual-metrics.csv', metrics)
    pointing = []
    for label, g in [('saved-timing', d), ('roof-fitted-c-timing', geometry['fitted-c']),
                      ('roof-zero-c-timing', geometry['zero-c']),
                      ('zero-timing', {k.removeprefix('unshifted_'): v for k, v in d.items() if k.startswith('unshifted_')})]:
        for rx in (0, 1):
            m = d['rx'] == rx
            record = dict(model=label, rx=rx, n=int(m.sum()),
                          west_fraction=float(np.mean(g['east_unit'][m] < 0)))
            for name in ('azimuth_deg', 'elevation_deg', 'own_off_axis_deg', 'other_off_axis_deg'):
                a = g[name][m]
                record[name] = dict(min=float(a.min()), median=float(np.median(a)), max=float(a.max()))
            pointing.append(record)
    np.savez_compressed(OUT / 'observations.npz', **d)
    dump(OUT / 'receipt.json', dict(scan='A', session_id='scan-fw-911c4e5db9243281', satellite=60412,
        scan_B_assigned_count=0, n=240, roof_timing_s=timing, metrics=metrics, pointing=pointing,
        selected_alternative_check=comparisons, sources={str(p): digest(p) for p in sources},
        scope='Same 240 frozen top-response greedy memberships in every comparison. No new fit or reassignment; newer roof score-fit parameters reused.',
        limitations=['Saved model used the old restaurant reference; roof model uses capture-bound operator coordinates.',
            'Polynomials are diagnostic, in-sample channel intercepts plus shared slope/curvature, not applied orbital corrections.',
            'Nominal axes assume a level base. Measured beam pattern and RF boresights unavailable; channel mapping provisional.',
            'Count imbalance is not a receiver-gain measurement; reception opportunities/GLRT thresholds may differ.']))
    render(d, residuals, metrics, geometry)
    print(json.dumps(dict(pointing=pointing, comparisons=comparisons, roof_timing_s=timing), indent=2))


def render(d, residuals, metrics, geometry):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    def metric(model, arm, rx):
        return next(r for r in metrics if r['model'] == model and r['arm'] == arm and
                    r['rx'] == rx and r['channel'] == 0 and r['channel_controlled'])

    for arm in ('fitted-c', 'zero-c'):
        fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True, sharey=True)
        for row, model in enumerate(('saved', 'roof')):
            for rx in (0, 1):
                ax = axes[row, rx]; m = d['rx'] == rx
                t, ch, y = d['time_s'][m], d['channel'][m], residuals[model][arm][m]
                r = metric(model, arm, rx)
                line = diagnostic_prediction(t, y, ch, 1)
                quad = diagnostic_prediction(t, y, ch, 2)
                for c in np.unique(ch):
                    q = np.flatnonzero(ch == c); q = q[np.argsort(t[q])]
                    ax.scatter(t[q], y[q], s=22, color=COLORS[c], alpha=.8)
                    ax.plot(t[q], line[q], '--', color=COLORS[c], lw=1.3)
                    ax.plot(t[q], quad[q], '-', color=COLORS[c], lw=1.5)
                ax.axhline(0, color='.4', lw=.8); ax.grid(alpha=.15)
                label = 'Saved association model (old reference)' if model == 'saved' else 'Capture-roof score model (newer fit)'
                ax.set_title(f'{label}\nRX{rx} · {len(t)} windows · {np.ptp(t):.1f} s\n'
                             f"RMS {r['raw_rms_hz']:.1f} → +linear {r['linear_rms_hz']:.1f} → +quad {r['quadratic_rms_hz']:.1f} Hz")
                ax.set_ylabel('GLRT − calibrated orbit (Hz)'); ax.set_xlabel('Receive time (s)')
        fig.suptitle(f'60412 · scan A · residual audit · {arm}', fontsize=18, y=.99)
        handles = [Line2D([], [], marker='o', color=COLORS[c], ls='', label=f'CH{c}') for c in (1, 2, 4)]
        handles += [Line2D([], [], color='.2', ls='--', label='Channel offsets + shared linear'),
                    Line2D([], [], color='.2', label='Channel offsets + shared quadratic')]
        fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .95), ncol=5)
        fig.text(.5, .016, 'Identical frozen memberships in all panels; no reassignment. Native Hz. Diagnostic polynomials are in-sample, not orbit corrections.\n'
                 'RMS is about zero before additional detrending; both polynomial fits include separate channel constants. No new fitting of the saved orbit models.',
                 ha='center', fontsize=10)
        fig.tight_layout(rect=(0, .065, 1, .89)); fig.savefig(OUT / f'residuals-{arm}.png', dpi=160); plt.close(fig)

    fig = plt.figure(figsize=(13, 6.7))
    ax = fig.add_subplot(121, projection='polar'); bx = fig.add_subplot(122)
    ax.set_theta_zero_location('N'); ax.set_theta_direction(-1)
    ax.set_ylim(0, 45); ax.set_yticks([10, 20, 30, 40], ['80°', '70°', '60°', '50°'])
    ax.set_title('High-elevation sky view\nCenter = zenith; radial labels = elevation', pad=25)
    g = geometry['fitted-c']
    order = np.argsort(d['time_s'])
    ax.plot(np.deg2rad(g['azimuth_deg'][order]), 90-g['elevation_deg'][order], color='.5', lw=1)
    for rx, color, marker in [(0, '#0072b2', 'o'), (1, '#d55e00', 'x')]:
        m = d['rx'] == rx
        ax.scatter(np.deg2rad(g['azimuth_deg'][m]), 90-g['elevation_deg'][m], color=color, marker=marker,
                   s=24 if rx == 0 else 48, label=f'Assigned RX{rx}: {m.sum()} windows')
        az = 270 if rx == 0 else 90
        ax.scatter([np.deg2rad(az)], [20], color=color, marker='*', s=210)
        ax.annotate(f'RX{rx} nominal axis', (np.deg2rad(az), 20), xytext=(5, 12), textcoords='offset points', fontsize=9)
    # All RX1-assigned samples, distance to each axis, computed from the same direction.
    m = d['rx'] == 1; order = np.argsort(d['time_s'][m]); t = d['time_s'][m][order]
    bx.plot(t, g['other_off_axis_deg'][m][order], 'o-', ms=4, color='#0072b2', label='To west-pointing RX0 axis')
    bx.plot(t, g['own_off_axis_deg'][m][order], 'o-', ms=4, color='#d55e00', label='To east-pointing RX1 axis')
    bx.set_title('At the 51 RX1-assigned windows\nRX0 is geometrically closer throughout')
    bx.set_ylabel('Angular distance from nominal axis (degrees)'); bx.set_xlabel('Receive time (s)')
    bx.set_ylim(0, 60); bx.grid(alpha=.2); bx.legend(loc='upper right')
    ax.legend(loc='lower center', bbox_to_anchor=(.5, -.23))
    fig.suptitle('60412 is west of zenith — not behind the east-tilted receiver', fontsize=17)
    fig.text(.5, .035, 'Capture-bound roof; newer fitted-c timing. Nominal axes: elevation 70°, azimuth 270° / 90° (40° apart).\n'
             'No measured beamwidth: these are axes, not detection boundaries. Frozen assignments are not independent identity verification.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .12, 1, .91)); fig.savefig(OUT / 'sky-geometry.png', dpi=170); plt.close(fig)


if __name__ == '__main__':
    main()
