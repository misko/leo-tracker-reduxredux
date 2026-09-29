import importlib.util
from pathlib import Path


def test_fused_command_adaptation():
    path = Path(__file__).with_name('evaluate.py')
    spec = importlib.util.spec_from_file_location('fused_evaluate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = module.adapted_source()
    assert 'for path in [*paths, raw]:' in source
    assert 'str(raw)]' in source
    assert 'str(raw), str(region)]' not in source
    assert "args.top == 4 and args.radius == 2" in source
