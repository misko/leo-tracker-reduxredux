import json

import polish_full_data_timing_priors as polish


def record(score, fixed, success):
    return dict(objective=score, fixed_location=fixed, success=success,
                point_km=[0., 0.] if fixed else [1., 0.], vector=[0.]*8)


def test_better_roof_candidate_is_not_hidden_and_joint_fit_is_rechecked(tmp_path, monkeypatch):
    source = tmp_path/'source'; source.mkdir()
    output = tmp_path/'output'; output.mkdir()
    monkeypatch.setattr(polish, 'SOURCE', source); monkeypatch.setattr(polish, 'OUT', output)
    old = record(10., False, True)
    roof = record(12., True, False)
    saved = dict(best=old, roof=roof, records=[old, roof], distance_m=1000.)
    path = source/'N01-fitted-c-baseline.json'
    original = json.dumps(saved); path.write_text(original)
    monkeypatch.setattr(polish.experiment, 'load', lambda scan: (None, None, None))
    monkeypatch.setattr(polish.experiment, 'objective', lambda *args: None)
    monkeypatch.setattr(polish.experiment, 'timing_and_gradient', lambda *args: {})
    monkeypatch.setattr(polish, 'diagnostics', lambda obj, data, r: dict(
        converged=r['success'] and not r['fixed_location'], distance_m=1000., kkt=0.))
    calls = []
    def fitted(obj, vector, point, budget, fixed, radius_km):
        calls.append((fixed, budget, radius_km))
        return record(5. if fixed else 4., fixed, True)
    monkeypatch.setattr(polish, 'fit', fitted)
    polish.run(('N01', 'fitted-c', 'baseline'))
    result = json.loads((output/path.name).read_text())
    assert calls == [(True, 20., 4.), (False, 20., 4.)]
    assert result['best']['objective'] == 4.
    assert result['converged']
    assert result['continuation']['maximum_pass_budgets_s'] == [20., 20., 20.]
    assert path.read_text() == original
