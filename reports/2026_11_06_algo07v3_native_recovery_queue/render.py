"""Render the verified common-prefix recovery comparison, not a full-scan gain."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def tasks(row):
    result = {}
    for block in row['blocks']:
        if block['kind'] != 'training':
            continue
        for item in block['tasks']:
            label = item['item']
            if len(label) == 2:
                target = int(block['stage'].split('-')[1])
                label = [target, *label]
            key = tuple(label)
            if key in result:
                raise ValueError('Duplicate training job')
            result[key] = item
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    args = p.parse_args()
    report = Path(__file__).resolve().parent
    value = json.loads((args.root / 'result.json').read_bytes())
    verified = json.loads((args.root / 'verified.json').read_bytes())
    assert verified['bindings_unchanged'] and verified['saved_native_audit_exact']
    for name, sha in value['plan']['bindings'].items():
        paths = [Path(name)]
        if name.endswith('/tools/probe_algo07v3_native_recovery_queue.py'):
            paths.append(report / 'measured-probe.py')
        assert any(q.exists() and hashlib.sha256(q.read_bytes()).hexdigest() == sha
                   for q in paths), name
    rows = {r['side']: r for r in value['rows']}
    assert len(rows) == 2 and all(r['exact'] for r in rows.values())
    a, b = rows['baseline'], rows['candidate']
    pairs = [tasks(r) for r in (a, b)]
    assert pairs[0].keys() == pairs[1].keys()
    details = []
    for key in pairs[0]:
        aa, bb = (v[key] for v in pairs)
        assert aa['training_points'] == bb['training_points']
        assert aa['phase_changes'] == bb['phase_changes']
        details.append(dict(target=key[0], seed=key[1], arm=key[2],
                            baseline_s=aa['end'] - aa['start'],
                            candidate_s=bb['end'] - bb['start'],
                            baseline_cpu=aa['cpu_seconds'], candidate_cpu=bb['cpu_seconds'],
                            baseline_rss=aa['max_rss_kib'], candidate_rss=bb['max_rss_kib']))
    summary = dict(baseline_s=a['seconds'], candidate_s=b['seconds'],
                   reduction_pct=100 * (1-b['seconds']/a['seconds']),
                   baseline_cpu=a['cpu_seconds'], candidate_cpu=b['cpu_seconds'],
                   task_count=len(details), task_comparisons=details)
    def makespan(costs):
        slots = [0., 0., 0.]
        for cost in costs:
            i = min(range(3), key=slots.__getitem__)
            slots[i] += cost
        return max(slots)
    models = []
    for side in ('baseline', 'candidate'):
        local = sum(makespan([r[side+'_cpu'] for r in details if r['target'] == target])
                    for target in sorted({r['target'] for r in details}))
        common = makespan([r[side+'_cpu'] for r in details])
        models.append(dict(cost_source=side, per_target_queue_s=local, global_queue_s=common,
                           difference_s=local-common, simulated_not_measured=True))
    summary['fixed_cpu_cost_schedule_models'] = models
    for name in ('plan.json', 'verified.json', 'prefix.jsonl', 'result.json'):
        shutil.copyfile(args.root / name, report / name)
    (report / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    labels = ['Complete recovery', 'Annotation stages', 'Training queues', 'Scoring queues']
    for j, (side, row) in enumerate(rows.items()):
        values = [row['seconds'],
                  sum(r['seconds'] for r in row['stages'] if r['name'].endswith('-annotation')),
                  sum(r['end'] - r['start'] for r in row['blocks'] if r['kind'] == 'training'),
                  sum(r['end'] - r['start'] for r in row['blocks'] if r['kind'] == 'scoring')]
        axes[0].barh([i+(j-.5)*.35 for i in range(4)], values, height=.35, label=side)
    axes[0].set_yticks(range(4), labels)
    axes[0].invert_yaxis()
    axes[0].set_xlabel('Wall seconds — nested rows, do not add')
    axes[0].legend()
    for arm, marker in [('c0', 'o'), ('fitted_c', 'x')]:
        chosen = [r for r in details if r['arm'] == arm]
        axes[1].scatter([r['baseline_s'] for r in chosen], [r['candidate_s'] for r in chosen],
                        label=arm, marker=marker)
    limit = max(max(r['baseline_s'], r['candidate_s']) for r in details) * 1.05
    axes[1].plot([0, limit], [0, limit], 'k--', linewidth=1)
    axes[1].set_xlabel('Baseline training task seconds')
    axes[1].set_ylabel('Candidate training task seconds')
    axes[1].legend()
    fig.suptitle('DS26-0066: complete recovery from the same fresh native prefix')
    fig.savefig(report / 'comparison.png', dpi=150)
    plt.close(fig)
    lines = ['| Side | Recovery s | CPU s | Annotation s | Training queues s | Scoring queues s |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for side, row in rows.items():
        annotation = sum(r['seconds'] for r in row['stages']
                         if r['name'].endswith('-annotation'))
        training = sum(r['end']-r['start'] for r in row['blocks'] if r['kind'] == 'training')
        scoring = sum(r['end']-r['start'] for r in row['blocks'] if r['kind'] == 'scoring')
        lines.append(f"| {side} | {row['seconds']:.3f} | {row['cpu_seconds']:.3f} | "
                     f"{annotation:.3f} | {training:.3f} | {scoring:.3f} |")
    (report / 'measurements.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
