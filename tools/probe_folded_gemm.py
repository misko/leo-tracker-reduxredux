"""Check blocked GEMM against native coarse scores and final receiver outputs."""

import argparse
import json
import time
from pathlib import Path

import profile_algo07_glrt as fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--method', choices=['gemm', 'overlap_fft'], default='gemm')
    args = parser.parse_args()
    fixture.use_source(args.source_root)
    import numpy as np
    from experimental_folded_gemm import folded_gemm

    from leo.analysis.starlink import acquisition
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow, production_glrt

    item = json.loads((args.fixture/'input.json').read_text())['windows'][0]
    window = VerifiedFastWindow(item['sequence'], item['iq_sha256'], item['acquisition'],
                                item['target'], np.load(args.fixture/item['samples']),
                                item['sample_rate_hz'])
    original = acquisition._folded_anchor_score_grid_native
    calls = []

    def checked(*values, **keywords):
        began = time.perf_counter()
        reference = original(*values, **keywords)
        reference_seconds = time.perf_counter()-began
        began = time.perf_counter()
        result = folded_gemm(*values, correlation=args.method)
        candidate_seconds = time.perf_counter()-began
        np.testing.assert_allclose(result, reference, atol=1e-12, rtol=1e-12)
        np.testing.assert_array_equal(np.argmax(result, axis=1), np.argmax(reference, axis=1))
        calls.append(dict(reference_seconds=reference_seconds, candidate_seconds=candidate_seconds,
                          maximum_absolute_delta=float(np.max(np.abs(np.asarray(result)-reference))),
                          samples=len(values[0]), cfo_count=len(values[3]), symbols=len(values[4])))
        return result

    expected = {p['receiver_id']: p['candidates'] for p in item['expected_probes']}
    acquisition._folded_anchor_score_grid_native = checked
    result = production_glrt(window, tuple(item['receiver_ids']))
    exact = all(fixture.published_candidates(r) == expected[r.receiver_id] for r in result)
    fixture.PROFILE.write_new(args.output, dict(method=args.method, calls=calls,
                                               published_candidates_exact=exact,
                                               intermediate_tolerance=1e-12,
                                               production_modified=False))
    print(json.dumps(dict(calls=calls, published_candidates_exact=exact)))


if __name__ == '__main__':
    main()
