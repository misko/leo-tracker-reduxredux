"""Exact complete predictive-annotation comparison, including the prior prefix."""
import argparse
import hashlib
import json
from pathlib import Path


def compare(reference, candidate, earlier_inventory):
    actual = candidate['predictive_annotation']
    if actual != reference:
        fields = sorted(k for k in set(reference) | set(actual)
                        if reference.get(k) != actual.get(k))
        raise ValueError('Predictive annotation differs: '+', '.join(fields))
    prefix = {k:v for k,v in candidate.items() if k != 'predictive_annotation'}
    if prefix != earlier_inventory:
        raise ValueError('Preceding inventory/scientific prefix changed')
    return dict(exact=True, preceding_inventory_exact=True, full_pipeline_parity=False,
        scope='Complete timestamp schedule, all catalogue nominations, both-arm training metadata, '
              'every candidate held prediction/phase diagnostic and final identity annotation')


def run(args):
    paths = {name:getattr(args,name) for name in ('reference','candidate','earlier_inventory')}
    raw = {k:p.read_bytes() for k,p in paths.items()}
    result = compare(*(json.loads(raw[k]) for k in paths))
    result['inputs'] = {k:dict(path=str(paths[k]),sha256=hashlib.sha256(v).hexdigest())
                        for k,v in raw.items()}
    with args.output.open('x') as stream:
        json.dump(result,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference','candidate','earlier-inventory','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    run(parser.parse_args())
