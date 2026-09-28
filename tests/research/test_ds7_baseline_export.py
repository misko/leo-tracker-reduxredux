import importlib.util
from pathlib import Path

PATH = Path(__file__).parents[2] / "tools" / "ds7_export_baseline.py"
SPEC = importlib.util.spec_from_file_location("ds7_export_baseline", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_partition_is_deterministic_and_visit_scoped():
    values = [MODULE.partition("scan-fw-example", visit) for visit in range(30)]
    assert values == [MODULE.partition("scan-fw-example", visit) for visit in range(30)]
    assert any(values) and not all(values)
