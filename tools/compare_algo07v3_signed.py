"""External exact comparison to the archived incumbent entering cavity selection."""
import argparse
import hashlib
import json
from pathlib import Path

from compare_algo07v3_history import compare_persisted

FIELDS = dict(baseline_arms='arms', baseline_node='node', baseline_entries='entries',
              baseline_means='means', original_mask='keep', powers='powers', model='model')


def compare(archived, candidate):
    if archived['status'] != 'complete':
        raise ValueError('Archived cavity result is incomplete')
    signed = candidate['signed_policy']
    for old, new in FIELDS.items():
        compare_persisted(archived[old], signed[new], old)
    return dict(exact=True, compared_fields=FIELDS,
        scope='All archived signed incumbent arms/node/entries/means/mask/powers/model; '
              'not later cavity selection or final ALGO07 publication')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archived', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    archive_bytes, candidate_bytes = args.archived.read_bytes(), args.candidate.read_bytes()
    result = compare(json.loads(archive_bytes), json.loads(candidate_bytes))
    result.update(archived_path=str(args.archived), candidate_path=str(args.candidate),
        archived_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest())
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(result, sort_keys=True))
