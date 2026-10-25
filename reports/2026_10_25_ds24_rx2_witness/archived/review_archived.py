"""Plot archived measurements and rejection diagnostics; no new fit or score."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
POOL = Path('/srv/bulk/leo/research/ds24-identity-support-r01/witness/whole_scan_inventory.json')
PARENT = Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership/DS24-0013/parent.json')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inputs = [POOL, PARENT, SOURCE/'DS24-0013/tracks.json',
              SOURCE/'DS24-0013/observations.json',
              SOURCE/'family_cavity/position/DS24-0013.json', Path(__file__)]
    bindings = {str(p): sha(p) for p in inputs}
    selected = sorted(read(POOL)['selected'], key=lambda r: r['channel'])
    tracks = {r['key']: r for r in read(inputs[2])}
    observations = read(inputs[3])
    by_id = {r['observation_id']: r for r in observations}
    seed = {r['component']: r for r in read(inputs[4])['baseline_node']['seed']['rows']}
    coverage = read(PARENT)['coverage']
    used = {arm: set(value['accepted_observation_ids']) for arm, value in coverage.items()}
    assert used['c0'] == used['fitted_c']
    accepted = used['c0']
    fig, axes = plt.subplots(3, 3, figsize=(17, 9), layout='constrained')
    rows = []
    for i, owner in enumerate(selected):
        track = tracks[owner['component']]
        old = seed[owner['component']]
        ids = owner['observation_ids']
        assert track['observation_ids'] == ids
        assert not set(ids) & accepted
        time = np.asarray(track['times'])
        value = np.asarray(track['values'])
        assert np.array_equal(time, owner['times_s'])
        assert np.array_equal(time, old['times_s'])
        measured = np.asarray([by_id[k]['measured_cfo_hz'] for k in ids])
        shift = value-measured
        assert np.max(abs(shift-shift[0])) < 1e-7
        assert len(track['pieces']) == 1
        piece = track['pieces'][0]
        z = (time-piece['reference_time_s'])/piece['time_scale_s']
        polynomial = np.polynomial.legendre.legval(z, piece['coefficients_hz'])
        residual = value-polynomial
        old_residual = np.asarray(old['residual_hz'])
        rms = lambda x: float(np.sqrt(np.mean(np.asarray(x)**2)))
        assert abs(rms(residual)-track['residual_rms_hz']) < 1e-7
        assert abs(rms(old_residual)-old['rms_hz']) < 1e-7
        context = [r for r in observations if r['receiver'] == 2
                   and r['channel'] == owner['channel']
                   and time.min()-3 <= r['time_s'] <= time.max()+3]
        for is_used, color, label in [(True, '#bcbcbc', 'Baseline associated'),
                                     (False, '#e58c8c', 'Baseline unassociated')]:
            group = [r for r in context if (r['observation_id'] in accepted) == is_used]
            axes[i, 0].scatter([r['time_s'] for r in group],
                               [(r['measured_cfo_hz']+shift[0])/1000 for r in group],
                               s=13, color=color, alpha=.65, label=label)
        axes[i, 0].scatter(time, value/1000, s=18, color='#176da3', label='Selected native source')
        axes[i, 0].plot(time, polynomial/1000, color='#1f2933', lw=1, label='Archived polynomial')
        margin = max(4., float(np.ptp(value))/1000*.12)
        axes[i, 0].set_ylim(value.min()/1000-margin, value.max()/1000+margin)
        axes[i, 0].set_ylabel('Graph-branch CFO (kHz)')
        axes[i, 0].set_title(f'RX2 CH{owner["channel"]} · {len(ids)} points · degree {piece["degree"]}')
        axes[i, 1].scatter(time, residual, s=18, color='#176da3')
        axes[i, 1].plot(time, residual, lw=.8, color='#176da3')
        axes[i, 1].set_title(f'Polynomial residual: {rms(residual):.1f} Hz RMS')
        axes[i, 1].set_ylabel('CFO residual (Hz)')
        axes[i, 2].scatter(time, old_residual, s=18, color='#b43e35')
        axes[i, 2].plot(time, old_residual, lw=.8, color='#b43e35')
        axes[i, 2].set_title(f'Rejected {old["candidate_norad"]}: {rms(old_residual):.1f} Hz RMS')
        axes[i, 2].set_ylabel('Archived nomination residual (Hz)')
        for ax in axes[i]:
            ax.grid(alpha=.2)
            ax.set_xlabel('Scan time (s)')
        for ax in axes[i, 1:]:
            ax.axhline(0, color='black', lw=.8)
        rows.append(dict(component=owner['component'], points=len(ids),
                         graph_degree=piece['degree'], graph_residual_rms_hz=rms(residual),
                         graph_quality_status=track['quality_status'],
                         graph_quality_flags=track['diagnostics']['quality_flags'],
                         graph_adjacent_residual_correlation=track['diagnostics']['pieces'][0]['adjacent_residual_correlation'],
                         archived_nominee_norad=old['candidate_norad'],
                         archived_nomination_compatible=old['compatible'],
                         archived_nomination_rms_hz=rms(old_residual),
                         archived_nomination_bias_parameter_hz=old['bias_hz'],
                         graph_minus_measured_CFO_uniform_shift_hz=float(shift[0]),
                         original_points_retained=True))
    axes[0, 0].legend(fontsize=8)
    fig.suptitle('DS24-0013: three unused RX2 curves and their archived rejection\n'
                 'Existing artifacts only; no new orbit fit, source trimming or identity decision', fontsize=15)
    fig.savefig(HERE/'archived_curve_diagnostics.png', dpi=170)
    fig.savefig(HERE/'archived_curve_diagnostics.pdf')
    plt.close(fig)
    assert bindings == {str(p): sha(p) for p in inputs}
    payload = dict(rows=rows, input_sha256=bindings,
                   source_count=3, distinct_native_IDs=124,
                   plot_context_shift='Uniform saved graph-minus-native CFO shift applied to the entire channel context; no nearest-model wrapping',
                   new_fits=0, new_candidate_scores=0, GPS_used=False,
                   interpretation='Archived failures are not scores from the current nomination/cavity experiment; labels are not sent to nomination.')
    (HERE/'summary.json').write_text(json.dumps(payload, indent=2)+'\n')
    artifacts = ['summary.json', 'archived_curve_diagnostics.png', 'archived_curve_diagnostics.pdf', 'review_archived.py']
    (HERE/'seal.json').write_text(json.dumps({name: sha(HERE/name) for name in artifacts}, indent=2)+'\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
