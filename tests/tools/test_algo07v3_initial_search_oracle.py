import sys
from types import ModuleType

from algo07v3_initial_search_oracle import (
    RESULT_FIELDS,
    reference_conservative_recovery,
    reference_initial_search,
)


def test_external_oracle_removes_io_but_retains_search_and_declared_budgets(tmp_path, monkeypatch):
    calls = []

    def module(name, source, **namespace):
        path = tmp_path/(name+'.py')
        path.write_text(source)
        result = ModuleType(name)
        result.__file__ = str(path)
        result.__dict__.update(namespace)
        exec(compile(source, str(path), 'exec'), result.__dict__)
        monkeypatch.setitem(sys.modules, name, result)
        return result

    def numerical_fit(problem, start=(0., 0.), iterations=48):
        calls.append(('fit', problem, iterations))
        return problem

    module('investigate_dsx01_localization_failures', '''
def refreshed(scan, sigma, node, arm, control="baseline", rounds=5):
    return [fit((node, arm)) for _ in range(rounds)]
''', fit=numerical_fit)

    def discovery(scan, sigma, budget):
        calls.append(('discovery', budget))
        return list(range(budget))[::-1]

    def forbidden(*args, **kwargs):
        raise AssertionError('External oracle must not run preparation or publication')

    module('evaluate_ds23_phase_refreshed', '''
def fit_case(case, noise_mode="fixed150"):
    forbidden()
    candidates = fresh_discovery(scan, sigma, budget=4)
    selected = sorted(candidates)[:3]
    choices = []
    for node in selected:
        pair = {arm: refreshed(scan, sigma, node, arm) for arm in ("c0", "fitted_c")}
        choices.append(pair)
        write("not-created", pair)
        print("not-printed")
    zero = {arm: fit(("zero", arm)) for arm in ("c0", "fitted_c")}
    write("not-created", dict(status="complete", GPS_used=False, choices=choices,
        selected_hypothesis=0, zero_phase_control=zero, selection="scientific policy",
        unique_RF_hypotheses=len(candidates), fully_fitted_hypotheses=len(selected),
        same_observations_candidates_priors_bounds_and_budgets_in_c_pair=True,
        fresh_radio_seed_budget=4, RF_proposal_points=((0., 0.),), region_center=(10., 20.),
        box_width_km=25., noise_sigma_hz=sigma, seconds=forbidden()))
''', fresh_discovery=discovery, forbidden=forbidden, write=forbidden)
    result = reference_initial_search(object(), 150., seed_budget=5, branch_budget=2,
                                      rounds=2, iterations=7)
    assert set(result) == set(RESULT_FIELDS)
    assert result['unique_RF_hypotheses'] == result['fresh_radio_seed_budget'] == 5
    assert result['fully_fitted_hypotheses'] == 2
    assert calls[0] == ('discovery', 5)
    assert len(calls[1:]) == 10  # Two branches × two arms × two rounds, plus two controls.
    assert {c[2] for c in calls[1:]} == {7}
    assert [p['c0'][0] for p in result['choices']] == [(0, 'c0'), (1, 'c0')]
    assert result['selection'] == 'scientific policy'


def _original_infer_example(case):
    forbidden()  # noqa: F821
    winner = next(c for c in original['choices']  # noqa: F821
                  if c['hypothesis'] == original['selected_hypothesis'])  # noqa: F821
    scan = final_scan(case)  # noqa: F821
    if winner['empty']:
        write('not-created', dict(case=case, status='no_passing_calibration', GPS_used=False))  # noqa: F821
        return
    observations = read('not-read')  # noqa: F821
    write('not-created', dict(case=case, status='complete', node=winner['node'],  # noqa: F821
        observations=observations, scan=scan, seconds=forbidden(),  # noqa: F821
        algorithm='label', source_sha256=forbidden()))  # noqa: F821
    print('not-printed')


def test_conservative_oracle_keeps_explicit_inputs_and_original_failure_return(monkeypatch):
    for name, attributes in {
        'run_algo01_ds23_sample': dict(infer=_original_infer_example),
        'audit_ds23_algo01_coverage': dict(coverage=None),
        'evaluate_ds23_phase_refreshed': dict(extend_associations=None),
        'propagate_ds23_arc_positions': dict(PositionNormal=None),
    }.items():
        module = ModuleType(name)
        module.__file__ = __file__
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    initial = dict(choices=[dict(hypothesis=0, empty=False, node='native-hypothesis')],
                   selected_hypothesis=0)
    observations, scan = [dict(observation_id='native-1')], object()
    result = reference_conservative_recovery(scan, initial, observations)
    assert result == dict(status='complete', node='native-hypothesis',
                          observations=observations, scan=scan)
    initial['choices'][0]['empty'] = True
    assert reference_conservative_recovery(scan, initial, observations) == dict(
        status='no_passing_calibration', GPS_used=False)
