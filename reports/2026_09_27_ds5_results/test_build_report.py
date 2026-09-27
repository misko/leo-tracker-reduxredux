import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("ds5_report", Path(__file__).with_name("build_report.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_reject_mixed_reference():
    with pytest.raises(ValueError, match="different reference"):
        module.check_references({"reference": {"latitude_deg": 37.8}}, {"reference": {"latitude_deg": 37.9}})


def test_same_reference():
    value = {"reference": {"latitude_deg": 37.8, "longitude_deg": -122.4}}
    assert module.check_references(value, value) == value["reference"]
