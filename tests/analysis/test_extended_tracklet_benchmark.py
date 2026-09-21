import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    spec = importlib.util.spec_from_file_location(
        "benchmark_extended_tracklets", ROOT / "tools" / "benchmark_extended_tracklets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_visible_prefilter_rejects_future_epoch_and_non_starlink(monkeypatch):
    module = _module(monkeypatch)

    class Catalogue:
        names = ("STARLINK-OLD", "STARLINK-FUTURE", "OTHER-OLD")

        @staticmethod
        def element_epoch_utc_ns():
            return np.array([9, 11, 1])

    def fake_states(catalogue, indices, reference_ns, times):
        np.testing.assert_array_equal(indices, [0])
        shape = (1, len(times), 3)
        p = np.zeros(shape)
        p[..., 0] = 7000
        return p, np.zeros(shape), np.asarray(indices)

    monkeypatch.setattr(module, "state_arrays", fake_states)
    visible, causal_count = module.visible_candidates(
        Catalogue(), 10, np.array([6378.0, 0, 0]), np.array([0.0, 20.0])
    )
    np.testing.assert_array_equal(visible, [0])
    assert causal_count == 1
