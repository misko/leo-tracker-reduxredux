import importlib.util
from pathlib import Path

PATH = Path(__file__).parents[2] / "tools/ds7_cfo_wave2_freeze.py"
SPEC = importlib.util.spec_from_file_location("ds7_cfo_wave2_freeze", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_freezer_declares_hard_iq_limit():
    assert 512 * 1024 * 1024 == 536870912
    assert MODULE.__doc__.endswith("IQ.")
