"""Read saved, complete protocols; never select a model from window outcomes."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
DATA = REPORTS/'2026_10_16_dsx01_fast_association_losses'
SOURCES = ['S01', 'S02', 'S03', 'S04', 'S05']
LABELS = {'original': 'Original', 'fixed': 'Fixed profile', 'expanded': 'Expanded profile',
    'fixed-wide': 'Fixed + width continuation', 'expanded-wide': 'Expanded + width continuation',
    'bias1000': 'Constant-Hz residual (rejected transfer)'}
COLORS = dict(zip(LABELS, ['#555555', '#0072B2', '#D55E00', '#009E73', '#CC79A7', '#B28A00']))


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def rms(values):
    return float(np.sqrt(np.mean(np.asarray(values)**2))) if len(values) else None


def support(before, after):
    before, after = np.asarray(before, bool), np.asarray(after, bool)
    if before.shape != after.shape:
        raise ValueError('Aligned original observations required')
    missing = int((~before).sum())
    new, lost = int((after & ~before).sum()), int((before & ~after).sum())
    return dict(observations=len(before), original=int(before.sum()), assigned=int(after.sum()),
        new=new, lost=lost, net_missing_restored_pct=100*(new-lost)/missing if missing else None)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    bindings = {}

    def bind(path):
        bindings[str(path.relative_to(REPORTS))] = 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    def load_json(path):
        return json.loads(bind(path).read_text())

    previous = REPORTS/'2026_10_16_dsx01_iteration2'
    third = REPORTS/'2026_10_17_dsx01_iteration3'
    fourth = REPORTS/'2026_10_17_dsx01_iteration4'
    wide = load_json(third/'support/annealing/uniform_evaluation.json')['rows']
    expanded_wide = load_json(fourth/'expanded_annealing/evaluation.json')['rows']
    contexts = [json.loads(line) for line in bind(DATA/'context-observations.jsonl').read_text().splitlines()]
    by_source = {s: [r for r in contexts if r['source_id']==s] for s in SOURCES}
    regions, membership = read_csv(bind(DATA/'regions.csv')), read_csv(bind(DATA/'membership.csv'))
    indices = {}
    for region in regions:
        sid = region['source_id']
        lookup = {r['observation_id']:i for i, r in enumerate(by_source[sid])}
        indices[region['region_id']] = np.array([lookup[r['observation_id']] for r in membership
            if r['region_id']==region['region_id']], int)
    states, records = {}, {}
    for arm in ['fitted-c', 'zero-c']:
        for method in LABELS:
            if method=='original' and arm=='zero-c':
                continue
            for sid in SOURCES:
                if method=='original':
                    path = REPORTS/'2026_10_16_dsx01_models/results'/f'{sid}-full-fitted-c-original.json'
                elif method in ('fixed', 'expanded'):
                    path = previous/('results' if method=='fixed' else 'expanded-results')/f'{sid}-{arm}-profile.json'
                elif method=='bias1000':
                    path = fourth/'frequency_bias/results'/f'{sid}-{arm}-b1000-profile.json'
                elif method=='fixed-wide':
                    path = third/'support/annealing'/f'uniform_fit_{sid}_{arm}_annealing.json'
                else:
                    path = fourth/'expanded_annealing'/f'raw_fit_{sid}_{arm}_annealing.json'
                record = load_json(path)
                array_path = path.with_suffix('.npz')
                if method in ('fixed-wide', 'expanded-wide'):
                    rows = wide if method=='fixed-wide' else expanded_wide
                    row = next(r for r in rows if r['source_id']==sid and r['arm']==arm and r['method']=='annealing')
                    record = dict(record, full_scan=row['full'], endpoint_audit=row['audit'])
                    array_path = path.with_name(path.name.replace('uniform_fit_', 'uniform_eval_')
                        .replace('raw_fit_', 'eval_')).with_suffix('.npz')
                with np.load(bind(array_path)) as arrays:
                    state = dict(arrays)
                expected = np.array([r['time_s'] for r in by_source[sid]])
                np.testing.assert_allclose(state['times_s'], expected, atol=1e-9, rtol=0)
                if 'observation_id' in state:
                    np.testing.assert_array_equal(state['observation_id'], [r['observation_id'] for r in by_source[sid]])
                assert int(state['associated'].sum())==record['full_scan']['associated']
                records[arm, method, sid], states[arm, method, sid] = record, state
    comparisons, windows, timing = [], [], []
    for arm in ['fitted-c', 'zero-c']:
        for method in LABELS:
            if method=='original' and arm=='zero-c':
                continue
            original, assigned, paired_old, paired_new = [], [], [], []
            strict = 0
            for sid in SOURCES:
                old, new = states['fitted-c', 'original', sid], states[arm, method, sid]
                original.extend(old['associated'])
                assigned.extend(new['associated'])
                both = old['associated'] & new['associated']
                paired_old.extend(old['residual_hz'][both])
                paired_new.extend(new['residual_hz'][both])
                record = records[arm, method, sid]
                strict += bool(record.get('endpoint_audit', record.get('audit', {})).get('accepted', False))
                full = record['full_scan']
                for number, tau in full['total_timing_s'].items():
                    timing.append(dict(arm=arm, method=method, source_id=sid, satellite_number=number,
                        total_timing_s=tau, relative_timing_s=tau-full['common_timing_s']))
            group = []
            for region in regions:
                sid, rid = region['source_id'], region['region_id']
                ix = indices[rid]
                result = support(states['fitted-c', 'original', sid]['associated'][ix],
                    states[arm, method, sid]['associated'][ix])
                assert result['observations']==int(region['observation_count'])
                assert result['original']==int(region['original_associated_count'])
                group.append(dict(arm=arm, method=method, source_id=sid, region_id=rid, **result))
            windows.extend(group)
            result = support(original, assigned)
            assert result['observations']==20084 and sum(r['observations'] for r in group)==693
            comparisons.append(dict(arm=arm, method=method, **result,
                window_assigned=sum(r['assigned'] for r in group),
                major_windows=sum(r['net_missing_restored_pct']>=80 for r in group),
                strict_endpoints=strict, paired_original_rms_hz=rms(paired_old), paired_variant_rms_hz=rms(paired_new)))
    write_csv(HERE/'comparison.csv', comparisons)
    write_csv(HERE/'windows.csv', windows)
    write_csv(HERE/'timing.csv', timing)
    for arm in ['fitted-c', 'zero-c']:
        methods = [m for m in LABELS if (arm, m, 'S01') in states]
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.7), constrained_layout=True)
        for method in methods:
            values = np.sort(np.concatenate([abs(states[arm, method, s]['residual_hz'][states[arm, method, s]['associated']]) for s in SOURCES]))
            grid = np.geomspace(1., 1000., 300)
            axes[0].step(grid, np.searchsorted(values, grid, side='right')/20084, where='post',
                color=COLORS[method], label=LABELS[method])
            distance = np.sort([records[arm, method, s]['full_scan']['configured_reference_distance_km'] for s in SOURCES])
            grid = np.r_[.1, distance, 1000.]
            axes[1].step(grid, np.searchsorted(distance, grid, side='right')/5, where='post', color=COLORS[method])
        axes[0].set(xscale='log', xlim=(1, 1000), ylim=(0, 1), xlabel='Absolute assigned CFO residual (Hz)', ylabel='Fraction of all 20,084 original observations')
        axes[1].set(xscale='log', xlim=(.1, 1000), ylim=(0, 1), xlabel='Configured-reference position distance (km)', ylabel='Fraction of five recordings')
        axes[0].legend(fontsize=7)
        for axis in axes:
            axis.grid(alpha=.2)
        fig.suptitle(f'DSX01 complete development protocols, {arm}\nUnassigned observations remain in denominator; improved fit does not establish localization')
        fig.savefig(HERE/f'performance-{arm}.png', dpi=160)
        plt.close(fig)
        fig, axis = plt.subplots(figsize=(12, 5), constrained_layout=True)
        matrix = np.array([[next(r['assigned']/r['observations'] for r in windows
            if r['arm']==arm and r['method']==m and r['region_id']==region['region_id']) for region in regions] for m in methods])
        picture = axis.imshow(matrix, vmin=0, vmax=1, cmap='viridis', aspect='auto')
        for i, method in enumerate(methods):
            for j, region in enumerate(regions):
                row = next(r for r in windows if r['arm']==arm and r['method']==method and r['region_id']==region['region_id'])
                axis.text(j, i, f"{row['assigned']}/{row['observations']}", ha='center', va='center', fontsize=8,
                    color='black' if matrix[i, j]>.55 else 'white')
        axis.set_xticks(range(15), [r['region_id'].split('-')[-1] for r in regions])
        axis.set_yticks(range(len(methods)), [LABELS[m] for m in methods])
        axis.set(xlabel='Frozen DSX01 window', title=f'{arm}: all 15 windows; no per-window model selection')
        fig.colorbar(picture, ax=axis, label='Assigned fraction')
        fig.savefig(HERE/f'windows-{arm}.png', dpi=160)
        plt.close(fig)
    with (HERE/'receipt.json').open('w') as stream:
        json.dump(dict(code_sha256='sha256:'+hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            inputs=bindings, qualification='Read-only aggregation of sealed development receipts. Older NPZ exports omit observation IDs; their source-ordered timestamps and frozen source receipts are the alignment authority. Fitted-c/c0 are separate. Raw numerically rejected endpoints remain visible; no model promoted.'), stream, indent=2)
    print(json.dumps(comparisons, indent=2))


if __name__=='__main__':
    main()
