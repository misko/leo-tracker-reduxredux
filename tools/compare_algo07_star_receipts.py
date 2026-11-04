"""Verify process forests, including reads of earlier process receipts.

This qualifies process provenance only, not scientific or artifact equivalence.
Every exported byte is checked before auditing the recorded process ancestry.
"""
import argparse
import json
from pathlib import Path

from algo07_star_receipts import audit_catalogue
from diff_algo07_star_evidence import load_export

from leo.application.algo07_star import ALGORITHMS
from leo.cli.algo07_profile import write_new


def load_catalogue(root):
    catalogue, bindings = {}, {}
    for algorithm in ALGORITHMS:
        descriptor, files = load_export(root/algorithm)
        bindings[algorithm] = {key: descriptor[key] for key in
                               ('model_version', 'job_id', 'input_sha256')}
        for name, path in files.items():
            catalogue[algorithm+'/'+name] = dict(
                path=path, store_root=descriptor['source_store_root'],
                sha256=descriptor['files'][name],
                job_id=descriptor['job_id'], model_version=descriptor['model_version'],
                source_path=str(Path(descriptor['source_worker_root'])/
                                Path(name).relative_to('worker')))
    return catalogue, bindings


def compare(reference, candidate):
    a, ab = load_catalogue(reference)
    b, bb = load_catalogue(candidate)
    if ab != bb:
        raise ValueError('Different stage model, job or native input binding')
    ag, ar = audit_catalogue(a)
    bg, br = audit_catalogue(b)
    rows = []
    for name in sorted(ag.keys() | bg.keys()):
        x, y = ag.get(name), bg.get(name)
        rows.append(dict(group=name, reference_sha256=x and x['forest_sha256'],
                         candidate_sha256=y and y['forest_sha256'],
                         equal=x is not None and y is not None and x['forest'] == y['forest'],
                         reference_receipts=x and x['receipts'],
                         candidate_receipts=y and y['receipts']))
    return dict(schema_version=1, kind='algo07-star-process-provenance-comparison',
                bindings=ab, process_provenance_equal=all(row['equal'] for row in rows),
                reference_groups=len(ag), candidate_groups=len(bg),
                reference_process_ids=len(ar), candidate_process_ids=len(br), groups=rows,
                normalization='Verified PIDs, private-store prefixes and sorted read sets',
                scientific_parity_qualified=False, artifact_parity_qualified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.reference, args.candidate)
    write_new(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('groups', 'bindings')}))
    raise SystemExit(0 if result['process_provenance_equal'] else 1)
