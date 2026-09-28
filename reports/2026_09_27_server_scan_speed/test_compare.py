import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('server_scan_compare', Path(__file__).with_name('compare.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_decisions_and_support_are_not_hidden_by_float_tolerance():
    assert module.differences({'passed': True}, {'passed': False})
    assert module.differences({'epoch': 1}, {'epoch': 2})
    assert module.differences([1, 2], [1])
    assert module.differences({'score': 1.}, {})
    assert module.differences(float('nan'), float('nan'))


def test_float_tolerance_is_absolute_and_tight():
    assert not module.differences(.1, .1+1e-14)
    assert module.differences(.1, .1+1e-10)
    assert module.differences(1e8, 1e8+1e-5)
