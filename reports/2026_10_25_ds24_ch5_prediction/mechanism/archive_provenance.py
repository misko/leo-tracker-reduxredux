"""Trace saved CH5 labels/diagnostics without propagation or fitting."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
KEY = 'DS24-0013-RX2-CH5-T001-RF11940312500.000000'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def target(rows):
    return next(row for row in rows if row['component'] == KEY)


def main():
    paths = dict(discovery=SOURCE/'DS24-0013/fit_radio_noise.json',
                 algo01=SOURCE/'DS24-0013/result.json',
                 cavity=SOURCE/'family_cavity/position/DS24-0013.json',
                 tracks=SOURCE/'DS24-0013/tracks.json',
                 salvage=REPO/'tools/run_algo01_ds23_sample.py',
                 discovery_source=REPO/'tools/evaluate_ds23_phase_refreshed.py',
                 retained_gate=REPO/'tools/audit_ds23_algo01_coverage.py',
                 script=Path(__file__))
    hashes = {str(p): digest(p) for p in paths.values()}
    discovery, algo, cavity = (read(paths[k]) for k in ('discovery', 'algo01', 'cavity'))
    chosen = next(c for c in discovery['choices'] if c['hypothesis'] == discovery['selected_hypothesis'])
    first = target(chosen['node']['seed']['rows'])
    final = target(algo['final_node']['seed']['rows'])
    later = target(cavity['baseline_node']['seed']['rows'])
    changed = [k for k in first if first[k] != final[k]]
    assert sorted(changed) == ['candidate_index', 'candidate_norad']
    assert first['candidate_norad'] == 65871 and final['candidate_norad'] == 57450
    assert final == later
    assert digest(paths['salvage']) == algo['source_sha256']
    assert digest(paths['discovery_source']) == discovery['source_sha256']
    original = {a: target(v['metrics']['tracks']) for a, v in chosen['arms'].items()}
    salvage = target(algo['trims'])
    selected = salvage['selected']
    assert selected['points'] == 32 and selected['norad'] == 57450
    suffix = next(a for a in salvage['alternatives'] if a['start_index'] == 26 and a['stop_index'] == 57)
    reject = next(h for h in algo['post_salvage_history'] if KEY in h['rejected_components'])
    track = next(t for t in read(paths['tracks']) if t['key'] == KEY)
    assert len(track['observation_ids']) == 57
    t, y = np.asarray(track['times']), np.asarray(track['values'])
    piece = track['pieces'][0]
    z = (t-piece['reference_time_s'])/piece['time_scale_s']
    residual = y-np.polynomial.legendre.legval(z, piece['coefficients_hz'])
    assert abs(np.sqrt(np.mean(residual**2))-track['residual_rms_hz']) < 1e-7
    prefix_mask = np.arange(len(t)) < 32
    suffix_mask = np.arange(len(t)) >= 26
    assert int(np.sum(prefix_mask & suffix_mask)) == 6
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, layout='constrained')
    for mask, color, label in (
        (prefix_mask & ~suffix_mask, '#176da3', 'Selected historical prefix (32 points including overlap)'),
        (suffix_mask & ~prefix_mask, '#cf782b', 'Historical suffix alternative (31 points including overlap)'),
        (prefix_mask & suffix_mask, '#8154a2', 'Six points shared by both historical supports')):
        axes[0].scatter(t[mask], y[mask]/1000, color=color, s=24, label=label)
        axes[1].scatter(t[mask], residual[mask], color=color, s=24)
    axes[0].set_ylabel('Stored graph-branch CFO (kHz)')
    axes[0].legend(fontsize=9)
    axes[0].set_title('All 57 native points remain in the current experiment')
    axes[1].axhline(0, color='black', lw=.8)
    axes[1].set_ylabel('Archived quartic residual (Hz)')
    axes[1].set_xlabel('Scan time (s)')
    axes[1].set_title('Polynomial replay only; no new orbit fit or point removal')
    for ax in axes:
        ax.grid(alpha=.2)
    fig.suptitle('CH5 historical partial supports: these are overlapping alternatives, not independent witnesses')
    fig.savefig(HERE/'historical_supports.png', dpi=160)
    plt.close(fig)
    summary = dict(component=KEY, input_sha256=hashes,
        cached_seed=dict(first_label=65871, later_label=57450, changed_fields=changed,
                         cached_rms_hz=first['rms_hz'], residual_vectors_identical=True,
                         interpretation='Cached diagnostic was not recomputed during relabel; its originating fit is not established here.'),
        actual_discovery_fit={a:dict(norad=v['norad'], rms_hz=v['native_rms_hz'], compatible=v['compatible']) for a,v in original.items()},
        historical_selected_salvage=selected, historical_suffix_alternative=suffix,
        candidate_count=salvage['candidate_count'], supports_tested=salvage['supports_tested'],
        overlap_ID_count=6, phase_grid_step_s=.25,
        subsequent_rejection=reject,
        old_failure_gate_detail_available=False,
        retained_gate_masks_active_observations=True,
        unchanged_current_complete_points=57, new_propagations=0, new_fits=0, GPS_used=False,
        source_mutation='run_algo01_ds23_sample.salvage updates only candidate_index/candidate_norad and alias; cached diagnostics remain.')
    assert hashes == {str(p):digest(p) for p in paths.values()}
    (HERE/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    outputs = [Path(__file__), HERE/'summary.json', HERE/'historical_supports.png']
    (HERE/'seal.json').write_text(json.dumps({p.name:digest(p) for p in outputs}, indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('cached_seed','actual_discovery_fit','overlap_ID_count','new_fits')}))


if __name__ == '__main__':
    main()
