"""Verify both full-scan pairs and the DS26-0002 reversed-order repeat."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path

from check_algo07v3_publication import evidence_snapshot
from compare_algo07v3_runs import matched_requests, scientific_values

from leo.storage.localization_v3 import LocalizationV3Store


def read(path):
    return json.loads(path.read_bytes())


def verify(bindings):
    for path, sha in bindings.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha, path


def main(first, second, geometry):
    out = Path(__file__).resolve().parent
    records, references = [], {}
    pairs = [('DS26-0002', 'first', first), ('DS26-0002', 'reverse', first / 'reverse'),
             ('DS26-0066', 'first', second)]
    for scan, label, root in pairs:
        prefix = f'{scan}-{label}-'
        plan, comparison = read(root / 'plan.json'), read(root / 'comparison.json')
        assert comparison['exact_owned_science_and_artifacts']
        verify(plan['bindings'])
        verify(comparison['input_bindings'])
        for name in ('plan.json', 'comparison.json', 'baseline-sources.json'):
            (out / (prefix + name)).write_bytes((root / name).read_bytes())
        for side in plan['sequence']:
            clock = read(root / side / 'attempt/supervisor.json')
            assert clock['status'] == 'exited' and clock['returncode'] == 0
            assert clock['worker']['status'] == 'complete' and not clock['worker']['resumed']
            assert all(read(root / side / 'isolation.json')['checks'].values())
            request = read(root / f'{side}-request.json')
            saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
            if scan in references:
                ref_request, ref = references[scan]
                matched_requests(ref_request, request)
                scientific_values(ref['evidence'], saved['evidence'])
                assert evidence_snapshot(ref['evidence'], ref['pngs']) == (
                    evidence_snapshot(saved['evidence'], saved['pngs']))
                assert ref['pngs'] == saved['pngs']
            else:
                references[scan] = request, saved
            logs = [json.loads(line) for line in (root / side / 'attempt/worker.log')
                    .read_text().splitlines()]
            stages = {r['stage']: r['seconds'] for r in logs if r.get('event') == 'stage'}
            text = (root / f'{side}-process-time.txt').read_text()
            values = dict(line.strip().rsplit(': ', 1)
                          for line in text.splitlines() if ': ' in line)
            assert values['Exit status'] == '0'
            packet = saved['evidence']['presentation']
            records.append(dict(scan=scan, pair=label, side=side, seconds=clock['process_seconds'],
                                stages=stages, user_seconds=float(values['User time (seconds)']),
                                system_seconds=float(values['System time (seconds)']),
                                maximum_rss_kbytes=int(values[
                                    'Maximum resident set size (kbytes)']),
                                selected_model=packet['selected_model'], arms=packet['arms']))
            for name in (f'{side}-process-time.txt', f'{side}-resources-start.json',
                         f'{side}-resources-end.json'):
                (out / (prefix + name)).write_bytes((root / name).read_bytes())
            for name, path in {'supervisor.json': 'attempt/supervisor.json',
                               'isolation.json': 'isolation.json'}.items():
                (out / f'{prefix}{side}-{name}').write_bytes((root / side / path).read_bytes())
    means = {scan: {side: {field: statistics.mean(r[field] for r in records
                                                if r['scan'] == scan and r['side'] == side)
                           for field in ('seconds', 'user_seconds', 'system_seconds')}
                    for side in ('baseline', 'candidate')} for scan in references}
    probe = read(geometry)
    assert probe['exact'] and not probe['runtime_modified']
    tool = Path('tools/probe_algo07v3_position_geometry.py')
    assert hashlib.sha256(tool.read_bytes()).hexdigest() == probe['tool_sha256']
    (out / 'geometry-probe.json').write_bytes(geometry.read_bytes())
    summary = dict(exact=True, cross_pair_science_and_pngs_exact=True, records=records, means=means,
                   qualified_speedup=None, full_historical_equivalence=False,
                   dataset_wide_qualification=False, production_modified=False)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), layout='constrained')
    colors = dict(baseline='#777777', candidate='#3465a4')
    for ax, scan in zip(axes, references, strict=True):
        selected = [r for r in records if r['scan'] == scan]
        bars = ax.bar([f'{r["side"]}\n{r["pair"]}' for r in selected],
                       [r['seconds'] for r in selected],
                       color=[colors[r['side']] for r in selected])
        ax.bar_label(bars, fmt='%.2f s', padding=4)
        ax.set(title=scan, ylabel='Native GLRT ready → publication/supervisor exit (s)',
               ylim=(0, max(r['seconds'] for r in selected) * 1.16))
    fig.suptitle('Exact full scientific outputs, both arms and all eight PNGs\n'
                 'Shared-host timing observations; capture, GLRT extraction and queue excluded')
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    print(json.dumps(dict(means=means, geometry_mean_seconds=probe['mean_seconds']), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first', type=Path, required=True)
    parser.add_argument('--second', type=Path, required=True)
    parser.add_argument('--geometry', type=Path, required=True)
    args = parser.parse_args()
    main(args.first, args.second, args.geometry)
