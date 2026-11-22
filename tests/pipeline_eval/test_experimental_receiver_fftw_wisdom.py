import ctypes as ct
import json

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental import receiver_fftw_wisdom as variant
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver


def test_missing_malformed_and_foreign_bundles_use_default(tmp_path, monkeypatch):
    machine = dict(machine="x86_64", fftw_version="single", cpu_sha256="matching")
    monkeypatch.setattr(variant, "hardware", lambda: machine)
    path = tmp_path / "wisdom.json"
    assert variant.read_wisdom(None) is None
    assert variant.read_wisdom(path) is None
    path.write_text("malformed")
    assert variant.read_wisdom(path) is None
    path.write_text(json.dumps(dict(hardware=dict(machine, cpu_sha256="foreign"), wisdom="text")))
    assert variant.read_wisdom(path) is None
    path.write_text(json.dumps(dict(hardware=machine, wisdom="measured text")))
    assert variant.read_wisdom(path) == b"measured text"


@pytest.mark.hardware
@pytest.mark.fftw
def test_native_default_and_all_three_fallback_produce_same_factors(tmp_path, monkeypatch):
    overlay = tmp_path / "fftw-overlay.so"
    variant.build(overlay)
    lib = ct.CDLL(str(overlay))
    # This valid wisdom has an unrelated tiny FFT and cannot supply even one
    # receiver plan. No receiver-size planner search is needed for the test.
    monkeypatch.setattr(variant, "SHAPES", [(16, -1)])
    incomplete = variant.measure(0.01)["wisdom"].encode("ascii")
    pilot = np.zeros(133413, dtype="<f4")
    samples = np.zeros((200000, 2, 2), dtype="<i2")
    factor_results = []
    try:
        for wisdom in (None, b"malformed native wisdom", incomplete):
            variant.configure(lib, wisdom, profile=True)
            receiver = Receiver(overlay, pilot)
            try:
                factor_results.append(receiver.timed(samples, 0, 0.0)[0])
            finally:
                receiver.close()
    finally:
        variant.configure(lib, None)
    assert factor_results[0] == factor_results[1] == factor_results[2]
    counts = variant.counters(lib)
    assert counts["estimate_calls"] == 3
    assert counts["fallback_calls"] == 2
    assert counts["wisdom_calls"] == 0
    assert counts["import_ns"] > 0
    assert counts["planning_ns"] > 0
