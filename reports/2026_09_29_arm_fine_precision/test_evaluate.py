import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('fine_experiment_evaluate', Path(__file__).with_name('evaluate.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_science_comparison_ignores_instrumentation_but_keeps_candidate_changes():
    base = {'receiver_id': 0, 'probe_index': 2, 'candidates': [{'margin': .025, 'epoch': 3}]}
    measured = dict(base, timings_ms={'total_cpu': 3}, fine_precision_fallbacks=1)
    assert module.science(base) == module.science(measured)
    changed = dict(measured, candidates=[{'margin': .02499, 'epoch': 3}])
    assert module.science(base) != module.science(changed)


def test_science_comparison_preserves_window_identity_and_multiplicity():
    base = {'receiver_id': 0, 'probe_index': 2, 'candidates': [{'margin': .04}]}
    assert module.science(base) != module.science(dict(base, receiver_id=1))
    assert module.science(base) != module.science(dict(base, candidates=base['candidates']*2))
