import importlib.util
from pathlib import Path

def test_threshold_boundary():
    spec=importlib.util.spec_from_file_location('coarse_gate_replay',Path(__file__).with_name('replay.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.keep({'coarse_score':.2},.2)
    assert not module.keep({'coarse_score':.199},.2)
