"""Compare saved adaptive phase estimates on exactly matching held-time blocks."""
import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

def wrap(x):
    return np.angle(np.exp(1j * x))

def rms_deg(x):
    return float(np.degrees(np.sqrt(np.mean(np.asarray(x) ** 2))))

def main():
    old = json.loads((ROOT / '2026_09_22_multi_dwell_track_phase/multi-dwell-results.json').read_text())
    new = json.loads(gzip.decompress((ROOT / '2026_09_22_adaptive_phase_fit/results.json.gz').read_bytes()))
    assert old['input_manifest_sha256'] == new['input_manifest_sha256']
    previous = {row['visit_index']: row for row in old['visits']}
    rows = []
    fig, axes = plt.subplots(4, 3, figsize=(14, 12), sharex=True, constrained_layout=True)
    for ax, row in zip(axes.flat, new['rows']):
        prior = previous[row['visit']]
        for key in ('reference_sample', 'frequency_reference_hz', 'relative_cfo_hz', 'relative_cfo_rate_hz_s', 'phase_rad'):
            assert np.isclose(prior['model'][key], row['model'][key], rtol=0, atol=1e-9), key
        a = prior['frequency_held_out_tracking']; b = row['held_out']
        t0 = np.array([r['center_sample'] for r in a['rows']])
        t1 = np.array([r['center_sample'] for r in b['rows']])
        np.testing.assert_array_equal(t0, t1)
        phase0 = np.array([r['training_band_phase_rad'] for r in a['rows']])
        phase1 = np.array([r['training_band_phase_rad'] for r in b['rows']])
        delta = wrap(phase1 - phase0)
        offset = float(np.angle(np.mean(np.exp(1j * delta))))
        centered = wrap(delta - offset)
        e0 = np.array([r['held_band_residual_phase_rad'] for r in a['rows']])
        e1 = np.array([r['held_band_residual_phase_rad'] for r in b['rows']])
        fit = np.interp(t1 / 2.5e6, row['time_s'], row['fitted_phase_rad'][row['selected_model']])
        ef = wrap(phase1 + e1 - fit)
        metrics = dict(visit=row['visit'], status=row['status'], time_ms=(t1 / 2500).tolist(),
                       new_minus_old_deg=np.degrees(delta).tolist(),
                       centered_difference_deg=np.degrees(centered).tolist(), offset_deg=float(np.degrees(offset)),
                       trajectory_change_rms_deg=rms_deg(centered),
                       old_B_A_rms_deg=rms_deg(e0), new_B_A_rms_deg=rms_deg(e1), new_B_fit_rms_deg=rms_deg(ef),
                       old_coherence=a['tracked']['coherence'], new_coherence=b['tracked']['coherence'],
                       old_wrong_time=a['wrong_time']['coherence'], new_wrong_time=b['wrong_time']['coherence'],
                       old_used_bandwidth_hz=a['training_bandwidth_hz'] + a['held_bandwidth_hz'],
                       new_used_bandwidth_hz=b['training_bandwidth_hz'] + b['held_bandwidth_hz'],
                       old_B_A_deg=np.degrees(e0).tolist(), new_B_A_deg=np.degrees(e1).tolist(),
                       new_B_fit_deg=np.degrees(ef).tolist())
        rows.append(metrics)
        ax.plot(t1 / 2500, np.degrees(delta), '--', color='gray', lw=1, label='New − old, native reference')
        ax.plot(t1 / 2500, np.degrees(centered), color='tab:blue', marker='.', ms=3, label='Constant offset removed')
        ax.axhline(0, color='black', lw=.6)
        ax.set_ylim((-180, 180) if row['visit'] == 724 else (-25, 25))
        ax.grid(alpha=.2)
        ax.set_title(f"Visit {row['visit']} · shape RMS {rms_deg(centered):.2f}°\noffset {np.degrees(offset):+.2f}° · {row['status']}")
    for ax in axes[-1]: ax.set_xlabel('Time within dwell (ms)')
    for ax in axes[:, 0]: ax.set_ylabel('New − previous phase (°)')
    axes[0, 0].legend(fontsize=7)
    fig.suptitle('Same IQ and timestamps: change in A-band phase after response refitting\n60–120 ms only; offset removal describes shape, not improved accuracy · visit 724 uses a wider scale')
    fig.savefig(HERE / 'phase-difference-all-visits.png', dpi=150)
    plt.close(fig)
    focus = next(r for r in rows if r['visit'] == 588)
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True)
    axes[0].plot(focus['time_ms'], focus['new_minus_old_deg'], '--', color='gray', label='Native new − old')
    axes[0].plot(focus['time_ms'], focus['centered_difference_deg'], '.-', label='Shape change, constant offset removed')
    for key, label in [('old_B_A', 'Previous direct B − A'), ('new_B_A', 'Updated direct B − A'), ('new_B_fit', 'Updated B − spline')]:
        axes[1].plot(focus['time_ms'], focus[key + '_deg'], '.-', label=f"{label}: {focus[key + '_rms_deg']:.2f}° RMS")
    for ax in axes:
        ax.axhline(0, color='black', lw=.6); ax.grid(alpha=.2); ax.legend()
        ax.set_xlabel('Time within visit 588 (ms)'); ax.set_ylabel('Phase difference (°)')
    fig.suptitle('Strong adaptive visit 588: small estimator change, larger cross-band scatter\nThe blue shape comparison removes a descriptive offset; validation residuals have no offset removed')
    fig.savefig(HERE / 'visit-588-differences.png', dpi=160)
    plt.close(fig)
    document = dict(session=new['session'], input_manifest_sha256=new['input_manifest_sha256'],
                    sign='new minus previous RX1-relative-to-RX0 A-band phase',
                    scope='same later-half time blocks; different response/masks; no equal-mask accuracy claim', rows=rows)
    (HERE / 'comparison.json').write_text(json.dumps(document, indent=2) + '\n')
    for r in rows:
        print(r['visit'], *(round(r[k], 3) for k in ['offset_deg', 'trajectory_change_rms_deg', 'old_B_A_rms_deg', 'new_B_A_rms_deg', 'new_B_fit_rms_deg', 'old_used_bandwidth_hz', 'new_used_bandwidth_hz']))

if __name__ == '__main__':
    main()
