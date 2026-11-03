"""Replay every grid and independently reprice all four variants' winners."""
from dataclasses import asdict, replace
import csv
import json
import numpy as np
import compare_variants as report
import run_variants as run
from leo.analysis.regional_position_score import PositionObjective, coordinates
from leo.analysis.regional_position_search import SpatialSearch, distinct_basins


def main():
    summary = report.read(run.HERE / 'summary.json')
    protocol = report.read(run.HERE / 'protocol.json')
    previous_protocol = report.read(run.OLD / 'protocol.json')
    reference_doc = report.read(run.OLD / 'evaluation.json')
    reference = [reference_doc['reference_latitude_deg'], reference_doc['reference_longitude_deg']]
    configs = {**previous_protocol['phases'], **run.PHASES}
    assert summary['complete'] and summary['completed_phases'] == 256
    assert len(summary['rows']) == 512
    with (run.HERE / 'comparison.csv').open() as handle:
        wide = list(csv.DictReader(handle))
    assert [r['label'] for r in wide] == run.LABELS
    rows = {(r['label'], r['phase'], r['arm']): r for r in summary['rows']}
    assert len(rows) == 512
    grids, selections, audits = [], [], []
    fit_calls = {phase: {arm: 0 for arm in report.ARMS} for phase in report.VARIANTS}
    bound_counts = {phase: dict(coarse=0, calibration=0, final=0) for phase in report.VARIANTS}
    for label in run.LABELS:
        _, obs, bank, prior, original_score = run.data.load(label)
        for phase in report.VARIANTS:
            cfg = configs[phase]
            folder = report.root(phase) / 'results' / label / phase
            search = report.read(folder / 'search.json')
            result = report.read(folder / 'result.json')
            assert result['config'] == cfg
            lookup = {(p['east_km'], p['north_km']): p['score'] for p in search['search']['evaluations']}
            replay, meta = run.engine.edge_grid.search(lambda ps: [lookup[tuple(xy)] for xy in ps],
                levels=cfg['levels'], budget=400, edge_policy=cfg['edge'])
            assert asdict(replay) == {**search['search'], 'evaluations': tuple(search['search']['evaluations'])}
            assert meta == search['edge'] and len(replay.evaluations) == 400
            supported = SpatialSearch(tuple(p for p in replay.evaluations if p.score < 1e100), replay.deferred_cells, replay.stop_reason)
            basins = distinct_basins(supported, count=3, minimum_separation_km=12.5)
            assert [asdict(b) for b in basins] == result['basins']
            width = cfg['width']
            if width is not None:
                for p in replay.evaluations:
                    point = report.read(folder / 'points' / f'{p.east_km:g}_{p.north_km:g}.json')
                    if 'fit' in point:
                        slopes = abs(np.asarray(point['fit']['vector'])[[3, 5]])
                        assert max(slopes) <= width + 1e-6
                        bound_counts[phase]['coarse'] += int(any(slopes >= width - 1e-6))
            candidates = []
            regions = {}
            for path in (folder / 'regions').glob('*.json'):
                region = report.read(path)
                regions[tuple(region['point'])] = region
                candidates.extend(dict(r, point=region['point'], local_radius_km=region['local_radius_km']) for r in region['candidates'])
                for r in region['runs']:
                    fit_calls[phase][r['arm']] += 1
                if width is not None:
                    for r in region['candidates']:
                        slopes = abs(np.asarray(r['vector'])[[3, 5]])
                        assert max(slopes) <= width + 1e-6
                        bound_counts[phase]['final'] += int(any(slopes >= width - 1e-6))
                    if 'calibration' in region:
                        for name in ('prefit', 'postfit'):
                            slopes = abs(np.asarray(region['calibration'][name]['vector'])[[3, 5]])
                            assert max(slopes) <= width + 1e-6
                            bound_counts[phase]['calibration'] += int(any(slopes >= width - 1e-6))
            for arm in report.ARMS:
                pool = [r for r in candidates if r['arm'] == arm and r['feasible'] and r['converged']]
                expected = min(pool, key=lambda r: (r['selection_score'], r['point'], r['origin']), default=None)
                assert expected == result['selections'][arm]['result']
                assert rows[label, phase, arm]['accepted'] == (expected is not None)
                if expected is not None:
                    region = regions[tuple(expected['point'])]
                    objective = PositionObjective(obs, bank.select(region['association']['selected_indices']), prior,
                        replace(original_score, relative_sigma_s=cfg['sigma']),
                        receiver_baseline_hz=np.asarray(region['calibration']['receiver_baseline_hz']))
                    vector = np.asarray(expected['vector'])
                    value, gradient, terms = objective.evaluate(vector)
                    np.testing.assert_allclose(value, expected['objective'], atol=1e-6, rtol=0)
                    row = rows[label, phase, arm]
                    latitude, longitude = coordinates(prior, vector[:2])
                    np.testing.assert_allclose([row['latitude_deg'], row['longitude_deg']],
                                               [latitude, longitude], atol=1e-10, rtol=0)
                    np.testing.assert_allclose(row['error_km'], report.distance_km(latitude, longitude, reference), atol=1e-9, rtol=0)
                    mass = float(terms.responsibilities.sum())
                    if mass > 1e-12:
                        rms = float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz ** 2) / mass))
                        np.testing.assert_allclose(row['frequency_rms_hz'], rms, atol=1e-8, rtol=0)
                    else:
                        assert row['frequency_rms_hz'] is None
                    checked = run.engine.audit(objective, vector, gradient, arm, expected['point'], expected['local_radius_km'], width)
                    assert checked['converged'] and checked['feasible']
                    if arm == 'zero-c':
                        assert vector[6] == 0.
                    audits.append(dict(label=label, phase=phase, arm=arm, **checked))
                selections.append(dict(label=label, phase=phase, arm=arm, accepted=expected is not None))
            grids.append(dict(label=label, phase=phase, replayed=True, points=400))
        print('VERIFIED', label, flush=True)
    for counts in fit_calls.values():
        assert counts['zero-c'] == counts['fitted-c']
    for path, expected in protocol['sources'].items():
        assert run.data.digest(path) == expected, path
    run.engine.write(run.HERE / 'validation.json', dict(all_checks_passed=True, grid_checks=grids,
        selection_checks=selections, original_score_audits=audits, final_fit_calls=fit_calls, slope_bound_counts=bound_counts))
    files = ['protocol.json', 'results.json', 'summary.json', 'comparison.csv', 'results_long.csv',
             'search_diagnostics.csv', 'findings.txt', 'validation.json', 'position_comparison.png',
             'per_scan_errors.png', 'position_comparison.svg', 'per_scan_errors.svg', 'compare_variants.py',
             'validate_comparison.py', 'run_variants.py', 'test_variants.py', 'tests.log', 'bootstrap_reuse.json', 'reproduction.txt']
    run.engine.write(run.HERE / 'artifact_manifest.json', dict(
        files={name: run.data.digest(run.HERE / name) for name in files},
        external_summary_helpers={str(run.OLD / 'summarize.py'): run.data.digest(run.OLD / 'summarize.py')},
        input_metadata=protocol['input_metadata']))
    print('PASS: 256 searches; 512 selections;', len(audits), 'original-score audits; matched final c fit calls', fit_calls)


if __name__ == '__main__':
    main()
