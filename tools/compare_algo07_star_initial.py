"""Compare the fresh initial stage through public exports, with zero tolerance.

This covers preparation and initial localization only. It does not qualify the
ALGO03–07 chain, publication, or DS26 as a cohort.
"""
import argparse
import json
from pathlib import Path

from profile_algo02_prepared import INPUTS, compare_results

from leo.cli.algo07_profile import destination, digest, write_new
from leo.storage.fast_graph_position import FastGraphPositionStore


def compare_preparation(left, right):
    rows = [dict(path=name, reference_sha256=digest(left/name),
                 candidate_sha256=digest(right/name)) for name in INPUTS]
    return dict(exact=all(r['reference_sha256'] == r['candidate_sha256'] for r in rows),
                files=rows, comparison='byte equality; no ignored preparation fields')


def run(reference, candidate, output):
    roots = [Path(p).resolve(strict=True) for p in (reference, candidate)]
    if roots[0] == roots[1]:
        raise ValueError('Independent private trials required')
    output = destination(output)
    if any(output == r or r.is_relative_to(output) or output.is_relative_to(r) for r in roots):
        raise ValueError('Comparison exports must be separate from both trials')
    sources = [json.loads((r/'algo07-star-input.json').read_text()) for r in roots]
    if any(s['kind'] != 'algo07-star-native-evidence' for s in sources):
        raise ValueError('Only isolated native-input trials are supported')
    if any(sources[0][k] != sources[1][k] for k in ('run_id', 'input_sha256', 'session_id')):
        raise ValueError('Trials used different observations')
    output.mkdir(parents=True, exist_ok=False)
    exports = []
    for label, root in zip(('reference', 'candidate'), roots, strict=True):
        store = FastGraphPositionStore(root)
        jobs = list(store.inputs())
        if len(jobs) != 1 or jobs[0]['input_sha256'] != sources[0]['input_sha256']:
            raise ValueError('Exactly one matching native input required per trial')
        descriptor = store.export_analysis(jobs[0], output/label)
        if not descriptor['terminal']['read_audit']['all_launched_processes_accounted']:
            raise ValueError('Production read audit did not account for every child')
        exports.append(output/label/'inference')
    preparation = compare_preparation(*exports)
    science = compare_results(*exports)
    result = dict(initial_stage_exact=preparation['exact'] and science['exact'],
                  preparation=preparation, scientific_results=science,
                  all_algo07_stages_compared=False, artifacts_compared=False,
                  ds26_equivalence_verified=False, production_modified=False)
    write_new(output/'comparison.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.reference, args.candidate, args.output)
    print(json.dumps({k:v for k,v in result.items()
                      if k not in ('preparation', 'scientific_results')}))
    if not result['initial_stage_exact']:
        raise SystemExit(1)
