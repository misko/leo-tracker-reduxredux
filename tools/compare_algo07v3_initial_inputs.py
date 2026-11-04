"""Exact initial-preparation comparison against a bound public worker export.

This oracle is external to the v3 input-preparation process. It does not compare
positions or subsequent recovery policies. Phase-history comparison is optional.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from diff_algo07_star_evidence import differences


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    descriptor_path = args.reference/'descriptor.json'
    descriptor = json.loads(descriptor_path.read_bytes())
    summary = json.loads((args.candidate/'summary.json').read_bytes())
    if summary['status'] != 'inputs_prepared' or summary['position_estimated'] is not False:
        raise ValueError('Complete preparation, not a position result, required')
    required = {'bank.npz', 'tracks.json', 'radio_noise.json', 'metadata.json',
                'selected.tle', 'previous.tle', 'genuine_previous.tle',
                'nominal_elements.json', 'previous_receipt.json', 'genuine_previous_receipt.json'}
    with_phase = getattr(args, 'with_phase_history', False)
    if with_phase:
        if not (getattr(args, 'reference_history_source', None)
                and getattr(args, 'reference_forecast_source', None)):
            raise ValueError('Phase comparison requires both reference source files')
        required |= {'phase_history.json', 'phase_forecast.json'}
    if not required <= summary['source_files'].keys():
        raise ValueError('Every compared candidate artifact must be bound')
    for name, expected in summary['source_files'].items():
        path = (args.candidate/name).resolve(strict=True)
        if not path.is_relative_to(args.candidate.resolve()) or digest(path) != expected:
            raise ValueError('Candidate artifact binding changed')

    def reference(name):
        path = (args.reference/name).resolve(strict=True)
        if (not path.is_relative_to(args.reference.resolve())
                or 'sha256:'+digest(path) != descriptor['files'][name]):
            raise ValueError('Reference export binding changed')
        return path

    source = 'worker/inference/SCAN/'
    prior = 'worker/inference/causal_prior/SCAN/'
    expected_native = 'sha256:'+digest(reference(source+'tracking.json'))
    if summary['input_sha256'] != expected_native:
        raise ValueError('Reference and candidate used different native input')
    checks = {}
    for name, original in [('selected.tle', source+'selected.tle'),
                           ('previous.tle', source+'previous.tle'),
                           ('genuine_previous.tle', prior+'previous.tle')]:
        checks[name] = (args.candidate/name).read_bytes() == reference(original).read_bytes()
    for name, original in [('nominal_elements.json', source+'nominal_elements.json'),
                           ('previous_receipt.json', source+'previous_receipt.json'),
                           ('genuine_previous_receipt.json', prior+'previous_receipt.json')]:
        checks[name] = not list(differences(json.loads(reference(original).read_bytes()),
                                          json.loads((args.candidate/name).read_bytes())))
    tracks = json.loads((args.candidate/'tracks.json').read_bytes())
    for name in ('observations', 'tracks'):
        checks[name] = not list(differences(json.loads(reference(source+name+'.json').read_bytes()),
                                          tracks[name]))
    prepared = json.loads(reference(source+'prepared.json').read_bytes())
    checks['native_metadata'] = not list(differences(prepared['metadata'], tracks['metadata']))
    noise = json.loads(reference(source+'radio_noise.json').read_bytes())
    for name, sha in noise.pop('source_sha256').items():
        if digest(reference(source+name)) != sha:
            raise ValueError('Original noise estimate has wrong observation/track binding')
    if noise.pop('code_sha256') != digest(args.reference_noise_source):
        raise ValueError('Original noise estimate implementation differs')
    checks['radio_noise'] = not list(differences(noise, json.loads(
        (args.candidate/'radio_noise.json').read_bytes())))
    metadata = json.loads((args.candidate/'metadata.json').read_bytes())
    receipt = json.loads(reference(source+'receipt.json').read_bytes())
    checks['sky_metadata'] = not list(differences({k:receipt[k] for k in metadata}, metadata))
    if with_phase:
        history_path = reference('worker/inference/causal_phase_history/SCAN.json')
        forecast_path = reference('worker/inference/causal_phase_history/SCAN_forecast.json')
        history = json.loads(history_path.read_bytes())
        forecast = json.loads(forecast_path.read_bytes())
        if (history.pop('source_sha256') != digest(args.reference_history_source)
                or history.pop('latest_elements_sha256') != digest(
                    reference(source+'nominal_elements.json'))
                or forecast.pop('source_sha256') != digest(args.reference_forecast_source)
                or forecast.pop('history_sha256') != digest(history_path)):
            raise ValueError('Reference phase provenance does not bind its inputs/code')
        new_history_path = args.candidate/'phase_history.json'
        new_forecast = json.loads((args.candidate/'phase_forecast.json').read_bytes())
        if new_forecast.pop('history_sha256') != digest(new_history_path):
            raise ValueError('Candidate forecast belongs to different history')
        checks['phase_history'] = not list(differences(
            history, json.loads(new_history_path.read_bytes())))
        checks['phase_forecast'] = not list(differences(forecast, new_forecast))
    with np.load(reference(source+'bank.npz')) as old, np.load(args.candidate/'bank.npz') as new:
        checks['bank_keys'] = set(old.files) == set(new.files)
        for name in set(old.files) & set(new.files):
            a, b = old[name], new[name]
            checks['bank/'+name] = (a.shape == b.shape and a.dtype == b.dtype
                                    and a.tobytes() == b.tobytes())
    scope = 'Initial tracks, causal elements, genuine prior, noise and bank'
    if with_phase:
        scope += ', phase history and forecast'
    result = dict(scope=scope,
                   exact=all(checks.values()), checks=checks, input_sha256=expected_native,
                   reference_descriptor_sha256=digest(descriptor_path),
                   candidate_summary_sha256=digest(args.candidate/'summary.json'),
                   reference_noise_source_sha256=digest(args.reference_noise_source),
                   phase_history_compared=with_phase,
                   full_localization_parity=False, pipeline_speedup_established=False)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result), flush=True)
    return int(not result['exact'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'reference-noise-source', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--with-phase-history', action='store_true')
    parser.add_argument('--reference-history-source', type=Path)
    parser.add_argument('--reference-forecast-source', type=Path)
    raise SystemExit(run(parser.parse_args()))
