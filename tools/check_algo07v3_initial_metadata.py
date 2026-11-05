"""Independently audit bookkeeping excluded from five initial scientific mappings.

This reads frozen external evidence only. It does not relax the scientific
comparator or qualify later policies, production admission, or the full dataset.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path

from compare_algo07v3_published import POLICIES, bound_link, read_export


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(root, runtime, manifest):
    root, runtime, manifest = (p.resolve(strict=True) for p in (root, runtime, manifest))
    frozen = json.loads(manifest.read_bytes())
    source_hashes = {r['path']: r['sha256'] for r in frozen['files']}
    checked, sources, exports = {}, {}, {}

    def expected(value, wanted, label):
        if value != wanted:
            raise ValueError(label + ' differs')

    def artifact(relative, digest):
        path = root / 'ALGO02' / relative
        if not path.resolve(strict=True).is_relative_to(root / 'ALGO02'):
            raise ValueError('Artifact escaped its export')
        expected(descriptor['files'][relative], 'sha256:' + digest, 'Export digest')
        expected(sha(path), digest, 'Artifact bytes')
        exports[relative] = digest

    def source(name, digest):
        path = runtime / 'tools' / name
        expected(source_hashes.get(str(path)), digest, 'Frozen source manifest')
        expected(sha(path), digest, 'Frozen source bytes')
        sources[str(path)] = digest

    names = ('initial', 'recovery', 'history_policy', 'cavity_nominations', 'cavity_policy')
    for name in names:
        stage, relative, inner, excluded = POLICIES[name]
        if stage != 'ALGO02' or inner is not None:
            raise ValueError('Review changed initial metadata mapping')
        value, descriptor = read_export(root, stage, relative)
        seconds = value['seconds']
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError('Elapsed time must be finite and nonnegative')
        handled = {'seconds'}
        if name in ('initial', 'recovery', 'history_policy'):
            expected(value['case'], 'SCAN', 'Case identity')
            handled.add('case')
        if name == 'initial':
            expected(value['noise_mode'], 'radio', 'Fixed radio-noise mode')
            artifact('worker/inference/SCAN/radio_noise.json', value['noise_features_sha256'])
            source('evaluate_ds23_phase_refreshed.py', value['source_sha256'])
            previous = bound_link(value['physical_prior_previous_tle_path'], descriptor,
                                  root / stage)
            expected(previous, 'worker/inference/SCAN/previous.tle', 'Previous TLE source')
            reads = [bound_link(path, descriptor, root / stage)
                     for path in value['input_read_paths']]
            wanted = ['worker/inference/SCAN/' + filename for filename in (
                'bank.npz', 'nominal_elements.json', 'previous.tle', 'radio_noise.json',
                'receipt.json', 'tracking.json', 'tracks.json')]
            expected(reads, wanted, 'Complete ordered initial input reads')
            handled.update(('noise_mode', 'noise_features_sha256', 'source_sha256',
                            'physical_prior_previous_tle_path', 'input_read_paths'))
        elif name == 'recovery':
            expected(value['algorithm'], 'ALGO01 batch composition', 'Recovery identity')
            source('run_algo01_ds23_sample.py', value['source_sha256'])
            handled.update(('algorithm', 'source_sha256'))
        elif name == 'history_policy':
            expected(value['algorithm'], 'ALGO02-v1', 'Family identity')
            source('algo02_scan.py', value['engine_sha256'])
            for field, path in (
                ('baseline_sha256', 'worker/inference/SCAN/result.json'),
                ('history_sha256', 'worker/inference/causal_phase_history/SCAN.json'),
                ('history_forecast_sha256',
                 'worker/inference/causal_phase_history/SCAN_forecast.json'),
            ):
                artifact(path, value[field])
            handled.update(('algorithm', 'engine_sha256', 'baseline_sha256',
                            'history_sha256', 'history_forecast_sha256'))
        elif name == 'cavity_policy':
            artifact('worker/inference/family_cavity/SCAN_nominations.json',
                     value['nomination_sha256'])
            handled.add('nomination_sha256')
        expected(handled, excluded, 'Every excluded field must have an explicit audit')
        checked[name] = sorted(handled)
    return dict(
        initial_metadata_links_verified=True, policies=checked,
        elapsed_time_semantics='finite nonnegative observations; elapsed values need not match',
        source=str(root), runtime=str(runtime), source_bindings=sources, artifact_bindings=exports,
        descriptor_sha256=sha(root / 'ALGO02/descriptor.json'),
        manifest=dict(path=str(manifest), sha256=sha(manifest)),
        tool=dict(path=str(Path(__file__).resolve()), sha256=sha(__file__)),
        remaining_scope='Later-policy metadata, ordinary admission, broader cases',
        full_intermediate_equivalence=False,
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('evidence', 'runtime', 'manifest', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.evidence, args.runtime, args.manifest)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(verified=True, policies=len(result['policies']),
                         fields=sum(map(len, result['policies'].values())))))
