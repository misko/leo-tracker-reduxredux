from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_second_replay_requires_both_arms_to_match_or_improve():
    source = (Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
              / "screened_graph_alias_trial.py")
    spec = spec_from_file_location(source.stem, source)
    trial = module_from_spec(spec)
    spec.loader.exec_module(trial)
    deployed = {"c0": 1.5, "fitted_c": 1.4}
    assert trial.qualifies(deployed, deployed)
    assert trial.qualifies({"c0": 1.0, "fitted_c": 1.3}, deployed)
    assert not trial.qualifies({"c0": 1.0, "fitted_c": 1.5}, deployed)
    assert not trial.qualifies({"c0": 1.0, "fitted_c": None}, deployed)
    assert not trial.qualifies({"c0": 1.0}, deployed)
