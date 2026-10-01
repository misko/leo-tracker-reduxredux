"""Audited first-start replay versus original three-start selection; no continuation."""
import argparse
import json
from pathlib import Path

import numpy as np
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent


def statistics(rows, key):
    errors = [r[key]['error_m'] for r in rows if r[key]['accepted']]
    if any(e is None or not np.isfinite(e) for e in errors):
        raise ValueError('Accepted outcome needs finite error')
    return dict(planned=len(rows), accepted=len(errors),
                median_m=float(np.median(errors)) if errors else None,
                p90_m=float(np.percentile(errors, 90)) if errors else None,
                max_m=max(errors) if errors else None,
                within_1km=sum(e <= 1000 for e in errors),
                within_3km=sum(e <= 3000 for e in errors))


def matched(rows):
    both = [r for r in rows if r['first']['accepted'] and r['baseline']['accepted']]
    deltas = [r['first']['error_m']-r['baseline']['error_m'] for r in both]
    return dict(jointly_accepted=len(both),
                first_only=sum(r['first']['accepted'] and not r['baseline']['accepted'] for r in rows),
                baseline_only=sum(r['baseline']['accepted'] and not r['first']['accepted'] for r in rows),
                neither=sum(not r['baseline']['accepted'] and not r['first']['accepted'] for r in rows),
                improves_over_1m=sum(d < -1 for d in deltas),
                worsens_over_1m=sum(d > 1 for d in deltas),
                ties_within_1m=sum(abs(d) <= 1 for d in deltas),
                median_change_m=float(np.median(deltas)) if deltas else None)


def summarize(rows):
    return {str(size): dict(first=statistics([r for r in rows if r['size'] == size], 'first'),
                           baseline=statistics([r for r in rows if r['size'] == size], 'baseline'),
                           matched=matched([r for r in rows if r['size'] == size])) for size in (1, 2, 4)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--blocks', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if len(set(args.blocks)) != len(args.blocks):
        raise ValueError('Duplicate blocks')
    inputs, frozen = {}, {}

    def read(path):
        value = sealed(path)
        inputs[str(path)] = digest(path)
        return value

    selection = read(HERE/'selection.json')
    units = [u for u in selection['evaluation_units'] if u['block_id'] in args.blocks]
    if len(units) != 7*len(args.blocks):
        raise ValueError('Unknown or incomplete block membership')
    rows = []
    for unit in units:
        name, block = unit['unit_id'], unit['block_id']
        directory = HERE/'first-start-replay-v1'/block/name
        block_summary = read(directory.parent/'summary.json')
        saved = next(r for r in block_summary['rows'] if r['unit'] == unit)
        source_freeze = read(directory/'sources.json')
        for mapping in ('source_sha256', 'inputs'):
            for path, expected in source_freeze[mapping].items():
                if path in frozen and frozen[path] != expected:
                    raise ValueError('Inconsistent source/input binding')
                frozen[path] = expected
        launch = read(directory/(name+'.launch.json'))
        audit_launch = read(directory/'audit-launch.json')
        if launch['freeze_sha256'] != digest(directory/'sources.json') or audit_launch != saved['audit_launch']:
            raise ValueError('Launch binding mismatch')
        parent_path = HERE/'independent-v2'/block/(name+'.json')
        original = read(parent_path)
        baseline_eval = read(parent_path.parent/'evaluation.json')
        baseline = next(r for r in baseline_eval['rows'] if r['unit'] == name)
        if baseline['receipt_sha256'] != digest(parent_path):
            raise ValueError('Baseline evaluation/parent mismatch')
        first = dict(accepted=False, error_m=None, failures=['Missing independent audit'])
        if (directory/(name+'.json')).exists():
            receipt = read(directory/(name+'.json'))
            if launch['receipt_sha256'] != digest(directory/(name+'.json')):
                raise ValueError('Replay receipt/launch mismatch')
            if receipt['replay']['parent_sha256'] != digest(parent_path) or Path(receipt['replay']['parent_path']) != parent_path:
                raise ValueError('Wrong parent lineage')
            expected = original['fits'][:1]
            if receipt['fits'] != expected or receipt['best'] != (expected[0] if expected and expected[0]['objectives'] else None):
                raise ValueError('Replay did not preserve unconditional first fit')
        if (directory/'evaluation.json').exists():
            evaluation = read(directory/'evaluation.json')
            if evaluation != saved['evaluation'] or len(evaluation['rows']) != 1 or evaluation['rows'][0]['unit'] != name:
                raise ValueError('Wrong replay evaluation')
            first = dict(evaluation['rows'][0])
        good_processes = all(l['returncode'] == 0 and l['within_budget'] and not l['timed_out'] for l in (launch, audit_launch))
        if not good_processes:
            first.update(accepted=False, error_m=None)
            first['failures'] = list(first['failures'])+['Replay or audit process failed']
        if not first['accepted']:
            first['error_m'] = None
        rows.append(dict(unit=name, block=block, dataset=block.split('-')[0], size=unit['size'],
                         first=first, baseline=baseline,
                         recorded_later_fit_seconds=sum(f['seconds'] for f in original['fits'][1:])))
    for path, expected in frozen.items():
        if digest(path) != expected:
            raise ValueError(f'Changed frozen source/input: {path}')
    result = dict(blocks=args.blocks, completed=len(rows), planned_full_panel=112,
                  pending=112-len(rows), summary=summarize(rows),
                  by_dataset={d: summarize([r for r in rows if r['dataset'] == d]) for d in ('DS9', 'DS10', 'DS11')},
                  rows=rows, inputs=inputs, frozen_sources_and_inputs=frozen,
                  sources={str(Path(__file__).resolve()): digest(__file__)},
                  qualification='Saved first-start replay with fresh numerical audits; baseline is original three-start, no continuation. Correlated development windows. Runtime fields inside replay evaluations are materialization only.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True)
    for ax, size, label in zip(axes, (1, 2, 4), ('Singles', 'Pairs', 'Quads')):
        local = [r for r in rows if r['size'] == size]
        valid = [r for r in local if r['first']['accepted'] and r['baseline']['accepted']]
        values = [r[k]['error_m'] for r in valid for k in ('baseline', 'first')]
        upper = max(values, default=1000)*1.1
        ax.plot([0, upper], [0, upper], '--', color='gray', linewidth=1)
        for dataset, color in zip(('DS9', 'DS10', 'DS11'), ('tab:blue', 'tab:orange', 'tab:green')):
            selected = [r for r in valid if r['dataset'] == dataset]
            ax.scatter([r['baseline']['error_m'] for r in selected], [r['first']['error_m'] for r in selected], label=dataset, color=color, alpha=.7)
        m = matched(local)
        ax.set_title(f'{label}: {len(valid)} jointly accepted\nFirst-only {m["first_only"]}; baseline-only {m["baseline_only"]}')
        ax.set_xlabel('Original three-start error (m)')
        ax.set_ylabel('First-start error (m)')
        ax.grid(alpha=.2)
    axes[0].legend()
    fig.suptitle(f'First-start replay: {len(rows)}/112 windows audited; below diagonal favors one start')
    fig.savefig(args.output.with_suffix('.png'), dpi=160)
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
