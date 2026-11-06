"""Archive completed initial-stage and optional native process-helper comparisons."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from profile_algo07v3_perf import parse_counters

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, action='append', default=[])
    args = parser.parse_args()
    output = Path(__file__).resolve().parent
    prepared = []
    for scan in ('0002','0066'):
        root = Path(f'/srv/bulk/leo-dev/algo07v3-idle-process-{scan}-20261106')
        raw = (root/'result.json').read_bytes()
        data = json.loads(raw)
        assert data['exact'] and all(r['exact'] for r in data['rows'])
        (output/f'prepared-{scan}.json').write_bytes(raw)
        sides = {r['side']:r for r in data['rows']}
        candidate, baseline = sides['candidate'], sides['baseline']
        prepared.append(dict(scan=scan, root=str(root), sha256=hashlib.sha256(raw).hexdigest(),
                             order=[r['side'] for r in data['rows']], exact=True,
                             baseline_wall=baseline['seconds'],candidate_wall=candidate['seconds'],
                             baseline_cpu=baseline['cpu_seconds'],candidate_cpu=candidate['cpu_seconds'],
                             borrowed_gradients=sum(t['borrowed_gradients']
                                                    for t in candidate['tasks']),
                             helpers=sum(t['cloned_problems'] for t in candidate['tasks'])))
    fig, axes = plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
    for ax,metric in zip(axes,('wall','cpu'),strict=True):
        for side,offset,color in (('baseline',-.18,'#4477aa'),('candidate',.18,'#cc6677')):
            bars = ax.bar(np.arange(2)+offset,[r[f'{side}_{metric}'] for r in prepared],
                          width=.36,label=side.title(),color=color)
            ax.bar_label(bars,fmt='%.1f',padding=3)
        ax.set_xticks([0,1],['DS26-0002','DS26-0066'])
        ax.set(ylabel='Elapsed seconds' if metric=='wall' else 'CPU seconds')
        ax.set_ylim(0,ax.get_ylim()[1]*1.12)
        ax.grid(axis='y',alpha=.2)
        ax.legend()
    fig.suptitle('Prepared complete initial search: bounded process helper\n'
                 'One pair per scan; full native evidence is reported separately')
    fig.savefig(output/'prepared.png',dpi=150)
    plt.close(fig)
    native = []
    for index,root in enumerate(args.native):
        destination = output/f'native-{index}'
        destination.mkdir(exist_ok=True)
        comparison = json.loads((root/'comparison.json').read_bytes())
        assert comparison['exact_owned_science_and_artifacts']
        plan = json.loads((root/'plan.json').read_bytes())
        for path, digest in plan['bindings'].items():
            original = Path(path)
            archived = output / ('measured-' + original.name)
            bound = archived if archived.exists() else original
            assert hashlib.sha256(bound.read_bytes()).hexdigest() == digest, path
        for name in ('comparison.json','plan.json'):
            (destination/name).write_bytes((root/name).read_bytes())
        rows = {}
        for side in ('baseline','candidate'):
            target = destination/side
            target.mkdir(exist_ok=True)
            for name in ('request.json','supervisor.json','worker.json','initial-tasks.json',
                         'counters.jsonl','worker.log','isolation.json','process-time.txt',
                         'resources-start.json','resources-end.json'):
                (target/name).write_bytes((root/side/name).read_bytes())
            timing = json.loads((target/'supervisor.json').read_bytes())
            events = [json.loads(line) for line in (target/'worker.log').read_text().splitlines()
                      if line.startswith('{')]
            initial = [row['seconds'] for row in events
                       if row.get('event') == 'stage' and row.get('stage') == 'initial']
            assert len(initial) == 1
            queue = json.loads((target/'initial-tasks.json').read_bytes())
            assert len(queue) == 1 and queue[0]['complete']
            rows[side] = dict(seconds=timing['process_seconds'],
                              initial_seconds=initial[0],
                              queue_cpu_seconds=queue[0]['cpu_seconds'],
                              counters=parse_counters(target/'counters.jsonl'))
        native.append(dict(root=str(root), exact=True, rows=rows))
    if native:
        fig, axes = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
        metrics = [('seconds', 'Complete worker seconds'),
                   ('initial_seconds', 'Targeted initial stage seconds'),
                   ('queue_cpu_seconds', 'Initial-fit queue CPU seconds'),
                   ('cpu', 'Complete harness CPU seconds')]
        for ax, (metric, label) in zip(axes.ravel(), metrics, strict=True):
            values = []
            for side in ('baseline', 'candidate'):
                row = native[-1]['rows'][side]
                values.append(row['counters']['cpu_seconds'] if metric == 'cpu' else row[metric])
            bars = ax.bar(['Baseline', 'Experimental helper'], values,
                          color=['#4477aa', '#cc6677'])
            ax.bar_label(bars, fmt='%.1f', padding=3)
            ax.set(ylabel=label, ylim=(0, max(values)*1.15))
            ax.grid(axis='y', alpha=.2)
        fig.suptitle('Complete DS26-0066: candidate-first pair\n'
                     'Targeted stage is flat; queue CPU increases. Prototype not adopted.')
        fig.savefig(output/'native.png', dpi=150)
        plt.close(fig)
    summary = dict(prepared=prepared, native=native, production_modified=False,
                   integrated=False, cumulative_speedup=None)
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
