"""Fixed-coordinate, zero-nuisance acquisition support for one exposed quad."""
import fcntl
import json
from pathlib import Path
import sys
import time
import numpy as np
from run_window import prepare_window
from acquisition_dot import DotTrackLikelihood
from acquisition_blas import BlasTrackLikelihood
from screen_seed_prefix import digest, sealed
from regression_batch import verify_sources

HERE = Path(__file__).resolve().parent


def main():
    started = time.monotonic()
    output = HERE/'iteration96-window-diagnostic-v1.json'
    if output.exists(): raise FileExistsError(output)
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inputs, frozen = {}, {}

        def read(path):
            value = sealed(path); inputs[str(path)] = digest(path); return value

        single_dir = HERE/'iteration96-v1/DS9-B05-S2'
        quad_dir = HERE/'first-start-replay-v1/DS9-B05/DS9-B05-Q'
        receipts = []
        for folder, unit in ((single_dir, 'DS9-B05-S2'), (quad_dir, 'DS9-B05-Q')):
            freeze = read(folder/'sources.json')
            for key in ('source_sha256', 'inputs'):
                for name, expected in freeze[key].items():
                    assert name not in frozen or frozen[name] == expected
                    frozen[name] = expected
            receipt = read(folder/(unit+'.json'))
            evaluation = read(folder/'evaluation.json')
            assert len(evaluation['rows']) == 1 and evaluation['rows'][0]['unit'] == unit
            assert evaluation['rows'][0]['accepted']
            assert evaluation['rows'][0]['receipt_sha256'] == digest(folder/(unit+'.json'))
            receipts.append(receipt)
        verify_sources(frozen)
        single, quad = receipts
        labels = ('single_seed', 'single_endpoint', 'quad_seed', 'quad_endpoint')
        points = np.asarray([single['proposal']['seeds'][0], single['best']['mean'][:2],
                             quad['proposal']['seeds'][0], quad['best']['mean'][:2]])
        assert np.all(np.isfinite(points)) and np.all(np.linalg.norm(points, axis=1) <= 250)
        binding, scans, _, _, _ = prepare_window('DS9-B05-Q')
        assert binding == quad['binding']
        rows, maximum = [], 0.
        for scan, height, _ in scans:
            total = np.zeros(len(points)); old_cache = {}; new_cache = {}
            for _, track in scan.tracks:
                assert time.monotonic()-started < 85
                a = DotTrackLikelihood(track, scan.bank, scan.config, height, 4., geometry_cache=old_cache)(points, np.empty((1, 0)))[:, 0, :]
                b = BlasTrackLikelihood(track, scan.bank, scan.config, height, 4., geometry_cache=new_cache)(points, np.empty((1, 0)))[:, 0, :]
                np.testing.assert_array_equal(np.isfinite(a), np.isfinite(b))
                np.testing.assert_array_equal(np.isneginf(a), np.isneginf(b))
                assert not np.isnan(a).any() and not np.isnan(b).any()
                error = float(np.max(np.abs(a[np.isfinite(a)]-b[np.isfinite(b)])))
                assert error < 1e-6; maximum = max(maximum, error)
                maxima = a.max(axis=1)
                assert np.isfinite(maxima).all()
                total += maxima+np.log(np.exp(a-maxima[:, None]).sum(axis=1))
            rows.append(dict(scan=scan.unit_id if hasattr(scan, 'unit_id') else binding['scans'][len(rows)],
                             tracks=len(scan.tracks), scores=total.tolist(),
                             quad_minus_single_endpoint=float(total[3]-total[1])))
        sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
                   if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
                   and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
        sources[str(HERE/'ITERATION96_WINDOW_DIAGNOSTIC.md')] = digest(HERE/'ITERATION96_WINDOW_DIAGNOSTIC.md')
        verify_sources(frozen); verify_sources(inputs)
        total = np.sum([r['scores'] for r in rows], axis=0)
        result = dict(unit=binding['unit_id'], point_labels=labels, points_km=points.tolist(), rows=rows,
            total_scores=total.tolist(), total_quad_minus_single_endpoint=float(total[3]-total[1]),
            maximum_score_implementation_difference=maximum, elapsed_seconds=time.monotonic()-started,
            inputs=inputs, frozen_sources_and_inputs=frozen, sources=sources,
            qualification='Post-result, error-selected single case at four data-selected coordinates. '
            'Original acquisition log-sum-exp score with every nuisance fixed at zero. '
            'Not profiled likelihood, a calibrated Bayes factor, mode probability or a confidence rule. No fits.')
        with output.open('x') as stream: json.dump(result, stream, indent=2, allow_nan=False)
        output.with_suffix('.sha256').write_text(digest(output)+'\n')
        print(json.dumps({k: result[k] for k in ('rows', 'total_quad_minus_single_endpoint', 'maximum_score_implementation_difference', 'elapsed_seconds')}, indent=2))


if __name__ == '__main__': main()
