"""Read-only element-age/timing audit; no fitting or station coordinates."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]


def element_age_hours(recording_ns, epoch_ns):
    return (int(recording_ns) - int(epoch_ns)) / 3.6e12


def main():
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    sources_path = REPORTS/'2026_10_16_dsx01_fast_association_losses/sources.json'
    timings_path = REPORTS/'2026_10_17_dsx01_iteration4/frequency_bias/timing-pairs.csv'
    sources = json.loads(sources_path.read_text())
    with timings_path.open() as stream:
        timings = [r for r in csv.DictReader(stream) if r['arm'] == 'fitted-c']
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshots = archive.list_snapshots()
    rows = []
    for source in sources:
        sid = source['source_id']
        snapshot = next(s for s in snapshots if s.digest == source['tle_sha256']
            and s.collected_utc_ns == source['tle_collected_utc_ns'])
        catalogue = parse_element_sets(archive.read(snapshot))
        epochs = catalogue.element_epoch_utc_ns()
        lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
        selected = [r for r in timings if r['source_id'] == sid]
        numbers = sorted({int(r['satellite_number']) for r in selected})
        original_path = REPORTS/'2026_10_16_dsx01_models/results'/f'{sid}-full-fitted-c-original.npz'
        with np.load(original_path) as data:
            midpoint_s = .5*(float(data['times_s'].min())+float(data['times_s'].max()))
            support = {n: int(np.sum(data['associated'] & (data['satellite_number'] == n))) for n in numbers}
        midpoint_ns = source['first_sample_estimate_utc_ns'] + round(midpoint_s*1e9)
        positions, _, valid = propagate_candidate_states(catalogue, [lookup[n] for n in numbers],
            midpoint_ns, np.array([0.]), np.array([0., 5., 10.]))
        displacement = {int(catalogue.satellite_numbers[i]): float(np.linalg.norm(p[2, 0]-p[0, 0]))
            for i, p in zip(valid, positions)}
        for timing in selected:
            n = int(timing['satellite_number'])
            signed_age = element_age_hours(midpoint_ns, epochs[lookup[n]])
            rows.append(dict(source_id=sid, satellite_number=n, method=timing['method'],
                provider=snapshot.provider, snapshot_sha256=snapshot.digest,
                collection_utc_ns=snapshot.collected_utc_ns, element_epoch_utc_ns=int(epochs[lookup[n]]),
                recording_midpoint_utc_ns=midpoint_ns, signed_element_age_hours=signed_age,
                absolute_element_age_hours=abs(signed_age),
                original_associated_support=support[n],
                total_timing_s=float(timing['total_timing_s']),
                relative_timing_s=float(timing['relative_timing_s']),
                common_timing_s=float(timing['common_timing_s']),
                ecef_displacement_for_10s_shift_km=displacement.get(n)))
    assert len(rows) == 4*215
    with (HERE/'pairs.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    original = [r for r in rows if r['method'] == 'original']
    def summary(subset):
        age = np.array([r['absolute_element_age_hours'] for r in subset])
        delta = np.array([abs(r['relative_timing_s']) for r in subset])
        motion = np.array([r['ecef_displacement_for_10s_shift_km'] for r in subset
            if r['ecef_displacement_for_10s_shift_km'] is not None])
        return dict(pairs=len(subset), median_age_hours=float(np.median(age)),
            age_range_hours=[float(age.min()), float(age.max())],
            relative_over_10s=int(np.sum(delta > 10.)),
            median_abs_relative_timing_s=float(np.median(delta)),
            age_abs_relative_pearson=float(np.corrcoef(age, delta)[0, 1]) if len(subset)>2 else None,
            valid_10s_propagations=len(motion),
            displacement_10s_km_percentiles=np.percentile(motion, [0, 50, 100]).tolist())
    result = dict(qualification='Descriptive selected-object audit, not physical orbit-error truth or prior calibration. Ages evaluated at recording midpoint. Timing fits may absorb geography, calibration or identity errors. No station coordinates, new fitting or RF collection.',
        original=summary(original), original_supported_5=summary([r for r in original if r['original_associated_support']>=5]),
        by_source={s['source_id']:summary([r for r in original if r['source_id']==s['source_id']]) for s in sources},
        input_sha256={str(p.relative_to(REPORTS)):'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [sources_path, timings_path]},
        code_sha256='sha256:'+hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (HERE/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3), constrained_layout=True)
    colors = {'S01':'#4477AA', 'S02':'#EE6677', 'S03':'#228833', 'S04':'#CCBB44', 'S05':'#AA3377'}
    for axis, method in zip(axes, ['original', 'b1000-profile']):
        for source in sources:
            sid = source['source_id']
            group = [r for r in rows if r['method']==method and r['source_id']==sid]
            for supported, marker in [(True, 'o'), (False, 'x')]:
                use = [r for r in group if (r['original_associated_support']>=5)==supported]
                axis.scatter([r['absolute_element_age_hours'] for r in use],
                    [abs(r['relative_timing_s']) for r in use], color=colors[sid], marker=marker,
                    s=22, alpha=.65, label=sid if supported else None)
        axis.set(title=method, xlabel='Absolute element age at recording midpoint (hours)',
            ylabel='Absolute fitted relative timing (seconds)')
        axis.axhline(10., color='black', linestyle=':', linewidth=1)
        axis.grid(alpha=.2)
    axes[0].legend(ncol=3)
    fig.suptitle('Same 215 selected recording–satellite pairs; × has fewer than 5 original assignments\nFitted shifts are not measured TLE errors; latest bias model failed conditional prediction')
    fig.savefig(HERE/'age-vs-timing.png', dpi=160)
    plt.close(fig)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
