"""Validate the extracted propagation kernel against a public prepared bank.

This uses already-selected elements solely as a numerical unit oracle. It does
not qualify causal catalogue discovery or standalone satellite association.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3.orbits import regional_bank
from leo.sky.propagation import parse_element_sets


def main(args):
    descriptor = json.loads((args.export/'descriptor.json').read_text())
    names = ['bank.npz', 'selected.tle', 'receipt.json', 'tracks.json']
    inputs = {}
    for name in names:
        relative = 'worker/inference/SCAN/' + name
        path = args.export/relative
        digest = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
        if descriptor['files'][relative] != digest:
            raise ValueError('Changed public export member')
        inputs[name] = path
    receipt = json.loads(inputs['receipt.json'].read_text())
    tracks = json.loads(inputs['tracks.json'].read_text())
    catalogue = parse_element_sets(inputs['selected.tle'].read_text())
    result = regional_bank(catalogue, receipt['origin_utc_ns'],
                           max(t['times'][-1] for t in tracks),
                           screen_latitude_deg=receipt['regional_center'][0],
                           screen_longitude_deg=receipt['regional_center'][1])
    fields = {}
    with np.load(inputs['bank.npz']) as reference:
        for name, value in result['bank'].items():
            other = reference[name]
            equal = (value.shape == other.shape and value.dtype == other.dtype
                     and value.tobytes() == other.tobytes())
            fields[name] = dict(exact=equal, shape=list(value.shape),
                                maximum_absolute_difference=float(np.max(np.abs(value-other)))
                                if value.shape == other.shape else None)
    output = dict(exact=all(row['exact'] for row in fields.values()), fields=fields,
                   source_descriptor=str(args.export/'descriptor.json'),
                   source_descriptor_sha256=hashlib.sha256(
                       (args.export/'descriptor.json').read_bytes()).hexdigest(),
                   selected_elements_are_test_input_only=True,
                   causal_catalogue_selection_qualified=False, full_localization_parity=False)
    with args.output.open('x') as stream:
        json.dump(output, stream, indent=2)
        stream.write('\n')
    print(json.dumps(output), flush=True)
    return int(not output['exact'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(main(parser.parse_args()))
