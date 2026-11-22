from importlib import import_module
from pathlib import Path


def test_solver_comparison_preserves_detector_and_native_library_pins(monkeypatch):
    path = Path(__file__).resolve().parents[2]/"reports/ALGO08/single-core-2x"
    monkeypatch.syspath_prepend(str(path))
    trial = import_module("saved_repair_pair")
    base = dict(detector="a/receiver.so", detector_sha256="first", solver="shared-tables",
                tle_parser=dict(library="a/tle.so", sha256="orbits"), schedule="conditional-residual")
    other = dict(base, detector="b/receiver.so", solver="collapsed-repair",
                 tle_parser=dict(library="b/tle.so", sha256="orbits"))
    assert trial.normalized(base) == trial.normalized(other)
    assert trial.normalized(base) != trial.normalized(dict(other, detector_sha256="second"))
    assert trial.normalized(base) != trial.normalized(dict(other, tle_parser=dict(library="b/tle.so", sha256="other")))
    assert trial.normalized(base) != trial.normalized(dict(other, schedule="all"))
