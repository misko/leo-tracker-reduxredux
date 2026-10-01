"""Seal coordinate rankings before any reference-error evaluation."""
import time
START = time.monotonic()
import argparse
import fcntl
import json
from pathlib import Path
import sys
import numpy as np
from run_window import prepare_window
from acquisition_dot import DotTrackLikelihood
from acquisition_blas import BlasTrackLikelihood
from regression_batch import verify_sources
from screen_seed_prefix import digest, sealed
from window_candidate_policy import rank_targets

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('block'); args = parser.parse_args()
    manifest_path = HERE/'window-candidate-manifest-v1.json'
    manifest = sealed(manifest_path)
    block = next(b for b in manifest['blocks'] if b['block'] == args.block)
    output = HERE/'window-candidate-score-v1'/(args.block+'.json')
    if output.exists(): raise FileExistsError(output)
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for key in ('sources', 'inputs', 'frozen_sources_and_inputs'): verify_sources(manifest[key])
        binding, scans, _, _, _ = prepare_window(args.block+'-Q')
        assert binding['scans'] == block['scans']
        points = np.asarray([c['point_km'] for c in block['candidates']])
        matrix, track_counts, maximum = [], [], 0.
        for scan, height, _ in scans:
            total = np.zeros(len(points)); old_cache = {}; new_cache = {}
            for _, track in scan.tracks:
                assert time.monotonic()-START < 85
                old = DotTrackLikelihood(track, scan.bank, scan.config, height, 4., geometry_cache=old_cache)
                new = BlasTrackLikelihood(track, scan.bank, scan.config, height, 4., geometry_cache=new_cache)
                a = old(points, np.empty((1, 0)))[:, 0, :]
                b = new(points, np.empty((1, 0)))[:, 0, :]
                np.testing.assert_array_equal(np.isfinite(a), np.isfinite(b))
                np.testing.assert_array_equal(np.isneginf(a), np.isneginf(b))
                assert not np.isnan(a).any() and not np.isnan(b).any()
                error = float(np.max(np.abs(a[np.isfinite(a)]-b[np.isfinite(b)])))
                assert error < 1e-6; maximum = max(maximum, error)
                maxima = a.max(axis=1); assert np.isfinite(maxima).all()
                total += maxima+np.log(np.exp(a-maxima[:, None]).sum(axis=1))
            matrix.append(total.tolist()); track_counts.append(len(scan.tracks))
        decisions = rank_targets(block['candidates'], block['scans'], matrix, block['targets'])
        assert len(decisions) == 7
        sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
                   if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
                   and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
        sources[str(HERE/'WINDOW_CANDIDATE_PLAN.md')] = digest(HERE/'WINDOW_CANDIDATE_PLAN.md')
        for key in ('sources', 'inputs', 'frozen_sources_and_inputs'): verify_sources(manifest[key])
        result = dict(block=args.block, candidate_ids=[c['id'] for c in block['candidates']],
            scans=block['scans'], score_matrix=matrix, track_counts=track_counts, decisions=decisions,
            maximum_score_implementation_difference=maximum, elapsed_seconds=time.monotonic()-START,
            inputs={str(manifest_path): digest(manifest_path)}, sources=sources,
            qualification='Original zero-nuisance acquisition scores. Rankings depend only on available scan sets '
            'and scores; no reference coordinates or error fields accessed. Coordinate proposals, not refitted target states.')
        output.parent.mkdir(exist_ok=True)
        with output.open('x') as stream: json.dump(result, stream, indent=2, allow_nan=False)
        output.with_suffix('.sha256').write_text(digest(output)+'\n')
        print(json.dumps(dict(block=args.block, tracks=sum(track_counts), candidates=len(points),
                              maximum_score_error=maximum, elapsed_seconds=result['elapsed_seconds'])), flush=True)


if __name__ == '__main__': main()
