"""Read-only, source-aware diagnosis of missing reference segments."""
import json
import hashlib
import sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '2026_09_30_arm_fast_tracks/server-baseline/output'
sys.path.insert(0, str(HERE / 'evaluation'))
import compare_membership as m


def main():
    dest = HERE / 'longest-missing'
    dest.mkdir(exist_ok=True)
    so = m.read_observations(BASE / 'server-observations.tsv')
    ao = m.read_observations(BASE / 'arm-observations.tsv')
    ss = m.read_sources(BASE / 'server-candidate-map.tsv', so)
    ass = m.read_sources(BASE / 'arm-candidate-map.tsv', ao)
    refs = m.read_tracks(BASE / 'server-tracks.tsv', so).values
    outs = m.read_tracks(HERE / 'physical-arm-a250.tsv', ao).values
    settings = json.loads((HERE / 'evaluation/thresholds.json').read_text())
    comparison = json.loads((HERE / 'host-v2/arm-a250.membership.json').read_text())
    absent = set(comparison['primary']['input_unsupported_reference_indexes']
                 + comparison['primary']['supported_without_complete_output_indexes'])
    ordered = sorted((t for t in refs if t.index in absent),
                     key=lambda t: t.end_ns-t.start_ns, reverse=True)
    candidates = defaultdict(list)
    assigned = defaultdict(list)
    calls = {}
    raw_paths = sorted((HERE.parent / '2026_09_30_arm_full_scan_comparison/arm-v2').glob('batch-*.jsonl'))
    for path in raw_paths:
        begin = int(path.stem.split('-')[1])
        results = [value['result'] for line in path.read_text().splitlines()
                   if 'result' in (value := json.loads(line))]
        for offset, result in enumerate(results):
            assert result['sequence'] == offset
            calls[begin+offset] = result
    assert len(calls) == 2215
    for key, observation in ao.items():
        candidates[(observation.lane, ass[key])].append(observation)
    for track in outs:
        for p in track.points:
            assigned[(track.lane, ass[p.candidate])].append((track.index, p))
    origin = min(o.start_ns for o in so.values())
    details = []
    fig, axes = plt.subplots(6, 2, figsize=(16, 19), layout='constrained')
    for rank, ref in enumerate(ordered):
        spacing = settings['alias_spacing_hz'] * 11.2e9/ref.lane.rf_hz
        scale = 11.2e9/ref.lane.rf_hz
        metrics = [(m.membership_metrics(ref, out, so, ao, ss, ass, settings), out)
                   for out in outs if out.lane == ref.lane]
        metric, best = max(metrics, key=lambda pair: (pair[0]['consistent_source_count'],
                                                     pair[0]['in_span_output_purity']))
        rows = []
        for p in sorted(ref.points, key=lambda p: so[p.candidate].center_ns):
            source = ss[p.candidate]
            available = candidates[(ref.lane, source)]
            good = [o for o in available if m.circular_distance(
                o.measured_cfo_hz*scale-p.raw_cfo_hz, spacing) <= 2500]
            good_out = [i for i, q in assigned[(ref.lane, source)] if
                        m.circular_distance(q.raw_cfo_hz-p.raw_cfo_hz, spacing) <= 2500]
            raw = next(r for r in calls[source[0]]['rows'] if r['receiver_id'] == source[1])
            raw_reason = ('matching_input' if good else
                          'all_retained_peaks_coarse_gated' if not raw['candidates'] and
                          raw['retained_peak_count'] > 0 and
                          raw['coarse_gate_skipped_count'] == raw['retained_peak_count'] else
                          'no_serialized_candidates_other' if not raw['candidates'] else
                          'all_below_margin' if max(c['margin'] for c in raw['candidates']) < .025
                          else 'passing_wrong_cfo')
            rows.append(dict(source=list(source), time_s=(so[p.candidate].center_ns-origin)*1e-9,
                             server_cfo_hz=p.dealiased_cfo_hz,
                             arm_candidates=len(available), arm_consistent=len(good),
                             assigned_track_indexes=sorted(set(good_out)),
                             raw_detector_reason=raw_reason,
                             raw_coarse_skipped=raw['coarse_gate_skipped_count'],
                             raw_retained_peaks=raw['retained_peak_count'],
                             raw_executed_glrt_calls=raw['actual_executed_glrt_calls'],
                             closest_input_residual_hz=min((m.circular_distance(
                                 o.measured_cfo_hz*scale-p.raw_cfo_hz, spacing)
                                 for o in available), default=None)))
        t = np.array([r['time_s'] for r in rows])
        f = np.array([r['server_cfo_hz'] for r in rows])
        best_points = sorted((p for p in best.points if metric['consistent_source_count'] > 0
                              and ref.start_ns <= ao[p.candidate].center_ns
                              <= ref.end_ns), key=lambda p: ao[p.candidate].center_ns)
        bt = np.array([(ao[p.candidate].center_ns-origin)*1e-9 for p in best_points])
        predicted = np.interp(bt, t, f)
        bf = np.array([p.dealiased_cfo_hz for p in best_points])
        aligned = bf + np.round((predicted-bf)/spacing)*spacing
        ref_sources = {ss[p.candidate] for p in ref.points}
        extras = [dict(source=list(ass[p.candidate]), time_s=float(bt[i]),
                       interpolated_reference_residual_hz=float(aligned[i]-predicted[i]))
                  for i, p in enumerate(best_points) if ass[p.candidate] not in ref_sources]
        consistent_times = [r['time_s'] for r in rows if r['arm_consistent']]
        gaps = [(a, b) for a, b in zip(consistent_times, consistent_times[1:]) if b-a > 4]
        summary = dict(reference_index=ref.index, channel=ref.lane.channel, receiver=ref.lane.receiver,
                       start_s=(ref.start_ns-origin)*1e-9, end_s=(ref.end_ns-origin)*1e-9,
                       duration_s=(ref.end_ns-ref.start_ns)*1e-9, reference_sources=len(rows),
                       input_consistent=sum(bool(r['arm_consistent']) for r in rows),
                       no_arm_candidates=sum(not r['arm_candidates'] for r in rows),
                       only_inconsistent_arm_candidates=sum(bool(r['arm_candidates']) and
                           not r['arm_consistent'] for r in rows),
                       assigned_any=sum(bool(r['assigned_track_indexes']) for r in rows),
                       best_output_index=best.index, best_metrics=metric,
                       best_extra_sources_not_in_reference=extras,
                       raw_detector_reasons={reason: sum(r['raw_detector_reason'] == reason for r in rows)
                                             for reason in sorted({r['raw_detector_reason'] for r in rows})},
                       consistent_input_gaps_over_4s=gaps, points=rows)
        details.append(summary)
        if rank < 6:
            ax, residual = axes[rank]
            ax.plot(t, f/1000, '.-', color='#1764a0', lw=1, label='Server assigned points')
            has = np.array([bool(r['arm_consistent']) for r in rows])
            ax.scatter(t[has], f[has]/1000, s=35, facecolors='none', edgecolors='#259a5d',
                       label='Matching ARM detection exists')
            ax.scatter(t[~has], f[~has]/1000, marker='x', s=30, c='#bd2040',
                       label='No matching ARM detection')
            ax.plot(bt, aligned/1000, '.--', c='#d76a10', lw=.8,
                    label=f'Best ARM output #{best.index}')
            ax.set_title(f'Ref #{ref.index}: Ch{ref.lane.channel}/RX{ref.lane.receiver} · '
                         f'{summary["duration_s"]:.1f}s · input {summary["input_consistent"]}/{len(rows)}')
            ax.set_ylabel('Alias-aligned normalized CFO (kHz)')
            residual.axhspan(-2.5, 2.5, color='#259a5d', alpha=.12)
            residual.plot(bt, (aligned-predicted)/1000, '.', color='#d76a10')
            residual.axhline(0, color='gray', lw=.5)
            residual.set_title(f'Output coverage {metric["reference_source_coverage"]:.1%}; '
                               f'in-span source purity {metric["in_span_output_purity"]:.1%}')
            residual.set_ylabel('ARM minus interpolated server CFO (kHz)')
            for a in (ax, residual):
                a.grid(alpha=.2)
                a.set_xlabel('Seconds from first projected observation')
            if rank == 0:
                ax.legend(fontsize=7)
    fig.suptitle('Six longest server segments without a complete ARM match\n'
                 'Source membership determines the score; interpolated residuals are a visual diagnostic only.')
    fig.savefig(dest / 'longest-six.png', dpi=160)
    fig.savefig(dest / 'longest-six.pdf')
    plt.close(fig)
    (dest / 'diagnosis.json').write_text(json.dumps(details, indent=2)+'\n')
    receipt_paths = raw_paths + [BASE / f'{side}-{suffix}' for side in ('server', 'arm')
                                for suffix in ('observations.tsv', 'candidate-map.tsv')]
    receipt_paths += [BASE/'server-tracks.tsv', HERE/'physical-arm-a250.tsv',
                     HERE/'evaluation/thresholds.json', Path(__file__)]
    (dest/'input-hashes.json').write_text(json.dumps({str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                                     for p in receipt_paths}, indent=2)+'\n')
    for s in details:
        print(f'#{s["reference_index"]}: {s["duration_s"]:.2f}s; '
              f'input {s["input_consistent"]}/{s["reference_sources"]}; '
              f'no candidates {s["no_arm_candidates"]}; wrong CFO only {s["only_inconsistent_arm_candidates"]}; '
              f'best #{s["best_output_index"]}: {s["best_metrics"]["consistent_source_count"]} '
              f'purity {s["best_metrics"]["in_span_output_purity"]:.3f}; '
              f'extra sources {len(s["best_extra_sources_not_in_reference"])}')


if __name__ == '__main__':
    main()
