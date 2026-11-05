"""Exact scientific comparison of recovery inventory and the preceding cavity."""
import argparse
import hashlib
import json
from pathlib import Path


def compare(reference, candidate, earlier_cavity):
    actual = candidate['recovery_inventory']
    if actual != reference:
        fields = sorted(k for k in set(reference) | set(actual)
                        if reference.get(k) != actual.get(k))
        raise ValueError('Recovery inventory differs: '+', '.join(fields))
    prefix = {k:v for k,v in candidate.items() if k != 'recovery_inventory'}
    if prefix != earlier_cavity:
        raise ValueError('Preceding cavity scientific result changed')
    return dict(exact=True, preceding_cavity_exact=True,
        scope='Both reconstructed likelihood summaries, point owners, protected publication '
              'support, remaining graph inventory and ordered recovery targets',
        full_pipeline_parity=False)


def run(args):
    paths = {name:getattr(args, name) for name in ('reference', 'candidate', 'earlier_cavity')}
    contents = {k:p.read_bytes() for k,p in paths.items()}
    result = compare(*(json.loads(contents[k]) for k in paths))
    result['inputs'] = {k:dict(path=str(paths[k]), sha256=hashlib.sha256(v).hexdigest())
                        for k,v in contents.items()}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'earlier-cavity', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
