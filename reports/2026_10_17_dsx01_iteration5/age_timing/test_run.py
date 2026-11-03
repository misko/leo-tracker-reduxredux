import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('age_pilot_run', Path(__file__).with_name('run.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_counted_joint_and_detail_ports_do_not_double_count_internal_dispatch():
    class Model:
        marker = 'original metadata'
        calls = 0
        def evaluate_details(self, *args):
            self.calls += 1
            return (3., 4., 5., 6.), {'unchanged': True}
        def evaluate_joint(self, *args):
            return self.evaluate_details(*args)[0]
    raw = Model()
    counted = module.Counted(raw)
    assert counted.evaluate_joint(None, None) == (3., 4., 5., 6.)
    assert counted.evaluate_details(None, None)[1] == {'unchanged': True}
    assert raw.calls == counted.calls == 2
    assert counted.marker == 'original metadata'
