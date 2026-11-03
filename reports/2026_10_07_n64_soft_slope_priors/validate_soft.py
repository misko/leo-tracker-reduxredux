"""Independent base-likelihood plus analytic-prior audit and full grid replay."""
import argparse
from dataclasses import asdict, replace
import csv
import numpy as np
import analyze_soft as report
import run_soft as run
from leo.analysis.regional_position_score import PositionObjective, coordinates
from leo.analysis.regional_position_search import SpatialSearch, distinct_basins


def independent_penalty(vector, spec):
    """Scalar independent expression; do not call the optimization wrapper."""
    cost = 0.; gradient = np.zeros(len(vector))
    for i in (3, 5):
        b = float(vector[i])
        if spec['kind'] == 'gaussian':
            cost += b * b / (2 * spec['scale'] ** 2)
            gradient[i] = b / spec['scale'] ** 2
        elif spec['kind'] == 'smooth' and abs(b) > spec['onset']:
            excess = abs(b) - spec['onset']
            cost += excess * excess / (2 * spec['scale'] ** 2)
            gradient[i] = (1 if b > 0 else -1) * excess / spec['scale'] ** 2
        else:
            assert spec['kind'] in ('none', 'smooth')
    return cost, gradient


def validate(pilot_label=None):
    protocol = report.read(run.HERE / 'protocol.json')
    configs = {**report.read(run.OLD / 'protocol.json')['phases'],
               **report.read(run.PREVIOUS / 'protocol.json')['phases'], **run.PHASES}
    reference_doc = report.read(run.OLD / 'evaluation.json')
    reference = [reference_doc['reference_latitude_deg'], reference_doc['reference_longitude_deg']]
    if pilot_label:
        labels, phases = [pilot_label], list(run.PHASES)
        rows = {}
    else:
        labels, phases = run.LABELS, report.VARIANTS
        summary = report.read(run.HERE / 'summary.json')
        assert summary['complete'] and summary['completed_phases'] == 576 and summary['new_completed'] == 320
        assert len(summary['rows']) == 1152
        rows = {(r['label'], r['phase'], r['arm']): r for r in summary['rows']}
        assert len(rows) == 1152
        with (run.HERE / 'comparison.csv').open() as handle:
            wide = list(csv.DictReader(handle))
        assert [r['label'] for r in wide] == run.LABELS
    grids, selections, audits = [], [], []
    counts = {p: {a: 0 for a in report.ARMS} for p in phases}
    bounds = {p: dict(coarse=0, calibration=0, final=0, coarse_soft_penalty=0) for p in phases}
    for label in labels:
        _, obs, bank, prior, original_score = run.data.load(label)
        for phase in phases:
            cfg = configs[phase]
            spec = cfg.get('slope_prior', dict(kind='none'))
            folder = report.root(phase) / 'results' / label / phase
            search, result = report.read(folder / 'search.json'), report.read(folder / 'result.json')
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
                        vector = np.asarray(point['fit']['vector'])
                        slopes = abs(vector[[3, 5]])
                        assert max(slopes) <= width + 1e-6
                        bounds[phase]['coarse'] += int(any(slopes >= width - 1e-6))
                        bounds[phase]['coarse_soft_penalty'] += int(independent_penalty(vector, spec)[0] > 1e-12)
            candidates, regions = [], {}
            for path in (folder / 'regions').glob('*.json'):
                region = report.read(path)
                regions[tuple(region['point'])] = region
                candidates.extend(dict(r, point=region['point'], local_radius_km=region['local_radius_km']) for r in region['candidates'])
                for r in region['runs']:
                    counts[phase][r['arm']] += 1
                if phase in run.PHASES:
                    assert region['slope_prior_annotation'] == spec
                frozen = 0.
                if 'calibration' in region:
                    frozen, _ = independent_penalty(region['calibration']['postfit']['vector'], spec)
                    if phase in run.PHASES:
                        np.testing.assert_allclose(frozen, region['frozen_slope_penalty'], atol=1e-10, rtol=0)
                for r in region['candidates']:
                    vector = np.asarray(r['vector'])
                    if width is not None:
                        assert max(abs(vector[[3, 5]])) <= width + 1e-6
                        bounds[phase]['final'] += int(any(abs(vector[[3, 5]]) >= width - 1e-6))
                    cost, _ = independent_penalty(vector, spec)
                    np.testing.assert_allclose(r['objective'], r['data_nll'] + r['timing_penalty'] + cost, atol=1e-6, rtol=0)
                    np.testing.assert_allclose(r['selection_score'], r['objective'] + region['calibration_penalty'] + frozen, atol=1e-6, rtol=0)
                    if phase in run.PHASES:
                        np.testing.assert_allclose([r['slope_penalty'], r['frozen_slope_penalty']], [cost, frozen], atol=1e-10, rtol=0)
                if width is not None and 'calibration' in region:
                    for name in ('prefit', 'postfit'):
                        slopes = abs(np.asarray(region['calibration'][name]['vector'])[[3, 5]])
                        assert max(slopes) <= width + 1e-6
                        bounds[phase]['calibration'] += int(any(slopes >= width - 1e-6))
            for arm in report.ARMS:
                pool = [r for r in candidates if r['arm'] == arm and r['feasible'] and r['converged']]
                expected = min(pool, key=lambda r: (r['selection_score'], r['point'], r['origin']), default=None)
                assert expected == result['selections'][arm]['result']
                if rows:
                    assert rows[label, phase, arm]['accepted'] == (expected is not None)
                if expected is not None:
                    region = regions[tuple(expected['point'])]
                    objective = PositionObjective(obs, bank.select(region['association']['selected_indices']), prior,
                        replace(original_score, relative_sigma_s=cfg['sigma']),
                        receiver_baseline_hz=np.asarray(region['calibration']['receiver_baseline_hz']))
                    vector = np.asarray(expected['vector'])
                    value, gradient, terms = objective.evaluate(vector)
                    cost, extra_gradient = independent_penalty(vector, spec)
                    np.testing.assert_allclose(value + cost, expected['objective'], atol=1e-6, rtol=0)
                    np.testing.assert_allclose(value - terms.nll, expected['timing_penalty'], atol=1e-6, rtol=0)
                    checked = run.engine.audit(objective, vector, gradient + extra_gradient, arm,
                                               expected['point'], expected['local_radius_km'], width)
                    assert checked['converged'] and checked['feasible']
                    if arm == 'zero-c':
                        assert vector[6] == 0.
                    if rows:
                        row = rows[label, phase, arm]
                        latitude, longitude = coordinates(prior, vector[:2])
                        np.testing.assert_allclose([row['latitude_deg'], row['longitude_deg']], [latitude, longitude], atol=1e-10, rtol=0)
                        np.testing.assert_allclose(row['error_km'], report.distance_km(latitude, longitude, reference), atol=1e-9, rtol=0)
                        mass = float(terms.responsibilities.sum())
                        if mass > 1e-12:
                            rms = float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz ** 2) / mass))
                            np.testing.assert_allclose(row['frequency_rms_hz'], rms, atol=1e-8, rtol=0)
                        else:
                            assert row['frequency_rms_hz'] is None
                    audits.append(dict(label=label, phase=phase, arm=arm, slope_penalty=cost, **checked))
                selections.append(dict(label=label, phase=phase, arm=arm, accepted=expected is not None))
            grids.append(dict(label=label, phase=phase, replayed=True, points=400))
        print('VERIFIED', label, flush=True)
    for phase_counts in counts.values():
        assert phase_counts['zero-c'] == phase_counts['fitted-c']
    for path, expected in protocol['sources'].items():
        assert run.data.digest(path) == expected, path
    result = dict(all_checks_passed=True, grid_checks=grids, selection_checks=selections,
                  original_score_audits=audits, final_fit_calls=counts, slope_bound_counts=bounds)
    run.engine.write(run.HERE / (f'pilot_{pilot_label}_validation.json' if pilot_label else 'validation.json'), result)
    if not pilot_label:
        files = ['protocol.json', 'results.json', 'summary.json', 'comparison.csv', 'results_long.csv',
                 'search_diagnostics.csv', 'findings.txt', 'validation.json', 'analyze_soft.py', 'validate_soft.py',
                 'plot_soft.py', 'run_soft.py', 'slope_penalty.py', 'test_soft.py', 'tests.log', 'bootstrap_reuse.json', 'reproduction.txt']
        files.extend(p.name for p in run.HERE.glob('*.png'))
        files.extend(p.name for p in run.HERE.glob('*.svg'))
        run.engine.write(run.HERE / 'artifact_manifest.json', dict(files={name: run.data.digest(run.HERE / name) for name in files},
            helper_sources={str(run.OLD / 'summarize.py'): run.data.digest(run.OLD / 'summarize.py')}, input_metadata=protocol['input_metadata']))
    print('PASS:', len(grids), 'searches;', len(selections), 'selections;', len(audits), 'original-likelihood plus analytic-prior audits;', counts)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pilot-label')
    validate(pilot_label=parser.parse_args().pilot_label)
