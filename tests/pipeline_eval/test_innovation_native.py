import numpy as np
import pytest

from tools.pipeline_eval.qualification import innovation_native_trial
from tools.pipeline_eval.variants import innovation_native, innovation_noise


@pytest.mark.hardware
def test_compiled_innovations_preserve_recurrence_for_strided_and_reversed_columns(tmp_path):
    library = tmp_path / "innovation.so"
    innovation_native_trial.build(library)
    run = innovation_native.kernel(library)
    rng = np.random.default_rng(1604)
    for n in (1, 2, 77, 567):
        t = np.cumsum(rng.uniform(0.001, 1.1, n))
        ref = innovation_noise.InnovationFilter(t, 150, 200, 4)
        op = innovation_native.CompiledFilter(t, 150, 200, 4, run=run)
        raw = rng.normal(size=(n, 24))
        unaligned = np.ndarray((n, 7), dtype="f8", buffer=bytearray(8 * n * 7 + 1), offset=1)
        unaligned[:] = raw[:, :7]
        for values in (
            raw,
            raw[:, 1::2],
            raw[::-1, ::-3],
            np.asfortranarray(raw),
            raw[:, 1],
            unaligned,
            raw[:, :0],
        ):
            np.testing.assert_allclose(op @ values, ref @ values, rtol=1e-13, atol=1e-14)
            np.testing.assert_allclose(values.T @ op.T, (ref @ values).T, rtol=1e-13, atol=1e-14)
        np.testing.assert_allclose(op.constant, ref.constant, rtol=1e-13, atol=1e-14)
        assert op.nbytes == 8 * (6 * n - 1)
