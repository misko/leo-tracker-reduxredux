"""Export every completed stage through the graph component's diagnostic port."""
import argparse
import importlib
import json
from pathlib import Path

from leo.application.algo07_star import ALGORITHMS
from leo.cli.algo07_profile import destination, write_new
from leo.storage.fast_graph_worker_evidence import export_worker_evidence


def run(args):
    root = args.root.resolve(strict=True)
    receipt = json.loads((root/'algo07-star-input.json').read_text())
    if receipt['kind'] != 'algo07-star-native-evidence':
        raise ValueError('Private replay root required')
    output = destination(args.output)
    output.mkdir(parents=True, exist_ok=False)
    previous = None
    exported = []
    for number, algorithm in enumerate(ALGORITHMS, 1):
        suffix = '' if number == 1 else f'_v{number}'
        module = importlib.import_module('leo.storage.fast_graph_position'+suffix)
        store = getattr(module, 'FastGraphPositionStore'+
                        ('' if number == 1 else f'V{number}'))(root)
        if previous is None:
            jobs = list(store.inputs())
            if len(jobs) != 1 or jobs[0]['input_sha256'] != receipt['input_sha256']:
                raise ValueError('One matching native replay input required')
            job = jobs[0]
        else:
            job = store.job(previous)
        previous = store.status(job['job_id'])
        if not previous or previous['state'] != 'complete':
            raise ValueError(f'{algorithm} is not complete; partial export retained')
        descriptor = export_worker_evidence(store, job, output/algorithm)
        exported.append(dict(algorithm=algorithm, files=len(descriptor['files']),
                             descriptor=str(output/algorithm/'descriptor.json')))
        if algorithm == args.through:
            break
    result = dict(kind='algo07-star-stage-exports', input_sha256=receipt['input_sha256'],
                  stages=exported, scientific_parity_checked=False)
    write_new(output/'exports.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--through', choices=ALGORITHMS, default='ALGO07')
    run(parser.parse_args())
