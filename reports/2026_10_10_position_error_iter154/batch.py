"""Two serial shards; four explicit fresh continuation cells per member."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from execute import verify
from ports import HERE, PRIOR, POLICY, load


def authoritative_status(directory, label, branch, digest):
    folder = Path(directory) / branch
    terminal = folder / 'result.json'
    if terminal.exists():
        row = json.loads(terminal.read_text())
        if row['protocol_sha256'] != digest or row.get('label') != label or row.get('branch') != branch:
            raise ValueError('foreign condition/branch result')
        return row['status']
    claims = sorted((folder / 'slices').glob('*.started.json'))
    if not claims:
        return None
    done = sorted((folder / 'slices').glob('*.done.json'))
    expected = [p.with_name(p.name.replace('.started.json', '.done.json')) for p in claims]
    if set(done) != set(expected):
        raise ValueError('orphan claim; no retry')
    for claim, completed in zip(claims, expected):
        start, end = json.loads(claim.read_text()), json.loads(completed.read_text())
        if start['protocol_sha256'] != digest or end['protocol_sha256'] != digest:
            raise ValueError('foreign condition claim')
        if end.get('label') != label or end.get('branch') != branch:
            raise ValueError('foreign pending member/branch')
        if start.get('slice') != end.get('slice'):
            raise ValueError('pending slice mismatch')
        phase = 'baseline' if branch == 'native' else 'candidate'
        if start.get('phase') != phase:
            raise ValueError('pending phase mismatch')
    status = json.loads(done[-1].read_text())['status']
    if status != 'pending':
        raise ValueError('missing authoritative terminal')
    return status


def run_cell(invoke, read):
    terminal = {'complete', 'failed', 'budget-exhausted', 'not-run-search-failed'}
    status = read()
    for _ in range(POLICY['continuation_slices']):
        if status in terminal:
            return status
        if status not in (None, 'pending'):
            raise ValueError('unknown authoritative status')
        status = invoke()
    if status not in terminal:
        raise ValueError('slice cap reached without terminal receipt')
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('shard', type=int, choices=(0, 1))
    parser.add_argument('--protocol', type=Path, default=HERE / 'protocol.json')
    parser.add_argument('--output', type=Path, default=HERE / 'results')
    args = parser.parse_args()
    plan = json.loads(args.protocol.read_text())
    verify(plan)
    from leo.contracts.digests import canonical_digest
    digest = canonical_digest(plan)
    args.output.mkdir(parents=True, exist_ok=True)
    terminal = args.output / f'batch-{args.shard}.json'
    if terminal.exists():
        if json.loads(terminal.read_text())['protocol_sha256'] != digest:
            raise ValueError('foreign batch')
        return
    with (args.output / f'batch-{args.shard}.claim.json').open('x') as file:
        json.dump(dict(protocol_sha256=digest, shard=args.shard), file)
    rows = []
    for member in plan['members'][args.shard::2]:
        for condition in POLICY['conditions']:
            for branch in POLICY['discovery_policies']:
                cell_digest = canonical_digest(dict(plan, execution_condition=condition))
                def read():
                    return authoritative_status(
                        args.output / member['label'] / condition, member['label'], branch, cell_digest
                    )
                def invoke():
                    subprocess.run([sys.executable, str(HERE / 'execute.py'),
                                    member['label'], condition, branch, '--protocol',
                                    str(args.protocol), '--output', str(args.output)], check=True)
                    status = read()
                    if status is None:
                        raise ValueError('child produced no authoritative receipt')
                    return status
                row = dict(label=member['label'], condition=condition, branch=branch)
                try:
                    row['status'] = run_cell(invoke, read)
                except Exception as error:
                    row['controller_failure'] = repr(error)
                rows.append(row)
    with terminal.open('x') as file:
        json.dump(dict(protocol_sha256=digest, shard=args.shard, cells=rows), file, indent=2)


if __name__ == '__main__':
    main()
