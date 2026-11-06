"""Compare every real coarse projection before checking the complete screen."""

import argparse
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_screen_azimuth import operations, projection

from leo.analysis.localization_v3 import residual_screen
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v3.screen_geometry import _elevation_and_rate, phase_frequency_grids
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store


def main(request_path, output):
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        raise ValueError('Pin one CPU and one BLAS thread')
    root = output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), request_path, Path(__file__),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/probe_algo07v3_screen_azimuth.py'),
             Path('tools/algo07v3_preazimuth_screen_oracle.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(request_path.read_bytes())
    assert runtime_versions() == request['runtime']
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    packet = evidence['audit']['additional_recovery']['preflight']
    catalogue, expected = evidence['catalogue'], evidence['audit']['residual_screen']['screen']
    functions, sources = operations()
    assert ast.dump(ast.parse(inspect.getsource(_elevation_and_rate) + "\n\n" +
                                     inspect.getsource(phase_frequency_grids))) == ast.dump(
        ast.parse(sources['candidate']))
    before, checks, callbacks = fingerprint((packet, catalogue)), [], []

    def verified(bank, times, positions, **kwargs):
        old = functions['baseline'](bank, times, positions, **kwargs)
        current = phase_frequency_grids(bank, times, positions, **kwargs)
        exact = all((a.shape, a.strides, a.dtype, a.tobytes()) ==
                    (b.shape, b.strides, b.dtype, b.tobytes())
                    for aa, bb in zip(current, old, strict=True)
                    for a, b in zip(aa, bb, strict=True))
        row = dict(phase=float(kwargs['phase_seconds']), shape=current[0][0].shape,
                   positions=len(current), exact=exact)
        checks.append(row)
        if not exact:
            (root / 'failed-check.json').write_text(json.dumps(row, indent=2)+'\n')
            raise AssertionError('Real coarse projection differs')
        return current

    with projection(verified):
        actual = residual_screen.screen_candidates(
            packet, catalogue, SearchRegion(tuple(request['search_center'])),
            on_target=callbacks.append)
    exact = (fingerprint(actual) == fingerprint(expected)
             and fingerprint(callbacks) == fingerprint(expected['targets']))
    unchanged = before == fingerprint((packet, catalogue))
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
               for p, digest in bindings.items())
    result = dict(checks=checks, full_screen_exact=exact, unchanged_inputs=unchanged,
                  bindings=bindings, scientific_receipt=saved['sha256'], complete=True)
    (root / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    assert exact and unchanged and checks
    print(json.dumps(dict(checks=len(checks), full_screen_exact=exact)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(**vars(parser.parse_args()))
