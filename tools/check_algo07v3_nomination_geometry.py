"""Verify every reduced live nomination projection against the full point grid."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_nomination_points import candidate, nomination_grids, residual_screen

from leo.analysis.localization_v3.region import SearchRegion
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/probe_algo07v3_nomination_points.py'),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    packet = evidence['audit']['additional_recovery']['preflight']
    catalogue, expected = evidence['catalogue'], evidence['audit']['residual_screen']['screen']
    before = fingerprint((packet, catalogue))
    operation, _, _ = candidate()
    checks = []

    def verified(bank, t, query, positions, *, phase_seconds):
        reduced = nomination_grids(bank, t, query, positions, phase_seconds=phase_seconds)
        original = residual_screen.phase_frequency_grids(bank, t, positions,
                                                        phase_seconds=phase_seconds)
        exact = True
        for arm, full in zip(reduced, original, strict=True):
            for actual, values in zip(arm, full, strict=True):
                selected = values[:, query]
                exact &= (actual.dtype == selected.dtype and actual.shape == selected.shape
                          and actual.tobytes() == selected.tobytes())
        checks.append(dict(points=len(t), selected=len(query), satellites=len(bank['position_km']),
                           phase_s=float(phase_seconds), exact=bool(exact)))
        assert exact, 'Selected orbital projections differ'
        return reduced

    operation.__globals__['_nomination_grids'] = verified
    (args.output / 'plan.json').write_text(json.dumps(dict(bindings=bindings), indent=2) + '\n')
    complete = False
    try:
        actual = operation(packet, catalogue, SearchRegion(tuple(request['search_center'])))
        assert fingerprint(actual) == fingerprint(expected)
        assert before == fingerprint((packet, catalogue))
        assert len(checks) == 33 * len(packet['targets'])
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
                   for p, sha in bindings.items())
        complete = True
    finally:
        result = dict(checks=checks, complete=complete, full_screen_exact=complete,
                      bindings=bindings, scientific_receipt=saved['sha256'],
                      full_pipeline_speedup=None)
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(dict(complete=complete, checks=len(checks))))


if __name__ == '__main__':
    main()
