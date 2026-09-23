"""Isolated replay of production scoring with only the initial spacing changed."""
import argparse
import json
import multiprocessing
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_position import adaptive_best_first_search
from leo.analysis.adaptive_tle_prediction import RegionalTrackPredictionEvaluator, build_prediction_banks
from leo.cli.adaptive_tle_position import _point_factory, _worker_start, _worker_point, _candidate
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bulk-root', type=Path, default=Path('/srv/bulk/leo'))
    parser.add_argument('--tle-root', type=Path, default=Path('/var/lib/leo/tle'))
    parser.add_argument('--baseline', type=Path, default=Path(__file__).with_name('position-document.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Choose a fresh output path to preserve recorded evidence')
    baseline = json.loads(args.baseline.read_text())
    started = time.monotonic()
    source = ScannerTrackingInputStore(args.bulk_root)
    try:
        prepared = prepare_adaptive_tle_position_inputs(
            baseline['session_id'], inputs=source, archive=TleArchiveReader(args.tle_root))
    finally:
        source.close()
    for key in ('input_manifest_sha256', 'analysis_manifest_sha256', 'evidence_sha256'):
        assert getattr(prepared, key) == baseline[key], (key, 'input changed')
    assert json.loads(json.dumps(list(prepared.track_evidence))) == baseline['diagnostics']['track_evidence']
    print('Verified identical input, analysis, track evidence, and partitions', flush=True)
    banks, receipt = build_prediction_banks(prepared.catalogue, prepared.candidate_indices,
                                            prepared.start_utc_ns, prepared.tracks)
    print(f'Prediction banks ready after {time.monotonic()-started:.1f}s', flush=True)
    output = {'session_id': baseline['session_id'], 'levels_km': [50, 25, 12.5],
              'budget_points': 400, 'evidence_sha256': prepared.evidence_sha256,
              'prediction_bank': asdict(receipt), 'priors': [], 'baseline_checks': []}
    context = multiprocessing.get_context('fork')
    for prior in baseline['priors']:
        name, region = prior['name'], prior['region']
        lat, lon = region['center_latitude_deg'], region['center_longitude_deg']
        evaluator = RegionalTrackPredictionEvaluator(banks, _point_factory(lat, lon))
        with context.Pool(4, initializer=_worker_start, initargs=(evaluator,)) as pool:
            old = prior['selected']
            check = pool.map(_worker_point, [(old['east_km'], old['north_km'])])[0]
            assert np.isclose(check.residual_rmse_hz, old['capped_weighted_rmse_hz'], rtol=1e-10)
            output['baseline_checks'].append({'prior': name, 'saved_rmse_hz': old['capped_weighted_rmse_hz'],
                                               'replayed_rmse_hz': check.residual_rmse_hz})
            last = [time.monotonic(), 0]
            def evaluate(points):
                rows = pool.map(_worker_point, np.asarray(points).tolist())
                last[1] += len(rows)
                if time.monotonic() - last[0] > 20:
                    print(f'{name}: {last[1]}/400 points', flush=True)
                    last[0] = time.monotonic()
                return rows
            result = adaptive_best_first_search(evaluate, radius_km=region['radius_km'],
                                                levels_km=(50, 25, 12.5), budget_points=400)
        spacing = {(p['east_km'], p['north_km']): p['spacing_km']
                   for p in result.trace if p['event'] == 'evaluate'}
        winner = result.global_incumbent
        selected = _candidate(winner, spacing[(winner.east_km, winner.north_km)], lat, lon)
        item = {'name': name, 'region': region, 'selected': selected.model_dump(mode='json'),
                'search_complete': result.complete, 'stop_reason': result.stop_reason,
                'evaluated_point_count': len(result.all_evaluations),
                'finest_evaluated_point_count': len(result.finest_evaluations),
                'deferred_cell_count': len(result.deferred_cells),
                'trace': list(result.trace), 'frontier': [asdict(c) for c in result.deferred_cells],
                'selected_tracks': [asdict(t) for t in winner.tracks],
                'evaluated_points': [{'east_km': p.east_km, 'north_km': p.north_km,
                                      'capped_weighted_rmse_hz': p.residual_rmse_hz}
                                     for p in result.all_evaluations]}
        output['priors'].append(item)
        output['elapsed_s'] = time.monotonic() - started
        args.output.write_text(json.dumps(output, indent=2, allow_nan=False)+'\n')
        print(json.dumps({'prior': name, 'selected': item['selected'], 'elapsed_s': output['elapsed_s']}), flush=True)


if __name__ == '__main__':
    main()
