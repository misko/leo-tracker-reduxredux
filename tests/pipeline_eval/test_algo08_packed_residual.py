import ctypes as ct

import numpy as np
import pytest

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_packed_residual import build, packed_residual
from tools.pipeline_eval.variants.algo08_posterior_handoff import Capture, bind_export


@pytest.fixture(scope="module")
def binaries(tmp_path_factory):
    root = tmp_path_factory.mktemp("packed-residual")
    stock = native_bound.build(root / "stock")
    packed = root / "packed"
    build(packed)
    return stock, packed


@pytest.mark.parametrize("fitted", [False, True])
@pytest.mark.parametrize("interleaved", [False, True])
def test_native_updates_and_export_preserve_ordered_arithmetic(binaries, fitted, interleaved):
    stock_path, folder = binaries
    rng = np.random.default_rng(100)
    groups = np.repeat(np.arange(3), [19, 22, 34])
    if interleaved:
        groups = rng.permutation(groups)
    count = len(groups)
    shared = 3 + fitted
    features = np.column_stack((rng.normal(0., 8., (count, shared)), 20. * np.eye(3)[groups]))
    noise = rng.uniform(3., 10., count)
    values = rng.normal(0., 20., count)
    options = dict(
        powers=np.array([1., 0.25, 0.75]), prior_groups=np.r_[0, np.full(shared + 2, -1)]
    )
    stock = native_bound.NativeBound(stock_path)
    grid_library, bound_library = folder / "packed-grid.so", folder / "packed-bound.so"
    try:
        expected = stock(values, features, noise, groups, **options)
        assert stock.counts["activated"] == 1
        with packed_residual(bound_library, grid_library):
            packed = native_bound.NativeBound(stock_path)
            try:
                actual = packed(values, features, noise, groups, **options)
                assert packed.counts["activated"] == 1
            finally:
                packed.clear()

        factors = []
        for path in (folder / "reference-grid.so", grid_library):
            library = ct.CDLL(str(path))
            entry = library.nb_run_posterior
            capture = Capture(features.shape[1])
            ordinary = bind_export(entry, stock)

            def run(*args, readout=capture, compiled=entry):
                return readout.run(stock, compiled, args)

            try:
                stock.run = run
                exported = stock(values, features, noise, groups, **options)
            finally:
                stock.run = ordinary
            assert capture.valid()
            for key in expected:
                target = np.asarray(expected[key]).tobytes()
                assert np.asarray(exported[key]).tobytes() == target, key
                assert np.asarray(actual[key]).tobytes() == target, key
            factors.append((capture.lower.tobytes(), capture.order.tobytes()))
        assert factors[0] == factors[1]
    finally:
        stock.clear()
