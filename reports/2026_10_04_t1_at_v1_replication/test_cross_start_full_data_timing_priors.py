import json

import cross_start_full_data_timing_priors as cross


def test_same_eight_seeds_and_selection_by_score_not_truth(tmp_path, monkeypatch):
    source = tmp_path/'source'; source.mkdir()
    out = tmp_path/'out'; out.mkdir()
    monkeypatch.setattr(cross, 'SOURCE', source); monkeypatch.setattr(cross, 'OUT', out)
    for arm in cross.experiment.ARMS:
        for mode in cross.experiment.PRECISIONS:
            winner = arm == 'zero-c' and mode == 'tighter'
            best = dict(objective=5. if winner else 10., fixed_location=False, success=True,
                        point_km=[3., 0.] if winner else [.1, 0.], vector=[0.]*8)
            (source/f'N01-{arm}-{mode}.json').write_text(json.dumps(dict(best=best, records=[best], objective=best['objective'])))
    monkeypatch.setattr(cross.experiment, 'load', lambda scan: (None, None, None))
    monkeypatch.setattr(cross.experiment, 'objective', lambda *args: None)
    calls = []
    def reprice(obj, seed, arm, stage):
        calls.append(stage)
        return dict(seed, stage=stage)
    monkeypatch.setattr(cross.experiment, 'reprice', reprice)
    monkeypatch.setattr(cross.experiment, 'timing_and_gradient', lambda *args: {})
    monkeypatch.setattr(cross, 'diagnostics', lambda obj, data, r: dict(
        objective=r['objective'], converged=True, distance_m=r['point_km'][0]*1000, kkt=0.))
    def forbidden(*args, **kwargs):
        raise AssertionError('A repriced stationary solution needs no continuation')
    monkeypatch.setattr(cross, 'fit', forbidden)
    cross.run(('N01', 'fitted-c', 'baseline'))
    result = json.loads((out/'N01-fitted-c-baseline.json').read_text())
    assert len(calls) == len(set(calls)) == 8
    assert len(result['cross_start']['sources']) == 8
    assert result['objective'] == 5. and result['distance_m'] == 3000.
    assert result['cross_start']['available_seed_gain_nll'] == 5.
    assert result['cross_start']['maximum_pass_budgets_s'] == [20., 20., 20.]
