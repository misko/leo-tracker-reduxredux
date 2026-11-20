import hashlib
import importlib.util
import weakref
from functools import lru_cache
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants.v5_cavity_lifetime import dispose, overlay


def test_dispose_breaks_model_cache_cycles_without_mutating_result_data():
    problem = SimpleNamespace()
    block = np.full((128, 64), 17.0)

    @lru_cache(maxsize=8)
    def calculate(_):
        return {"features": block, "model": problem}

    problem.calculate = lambda x, call=calculate: call(x)
    problem.curved_calculate = calculate
    problem._fixed_phase_geometry_cache = (block,)
    assert problem.calculate(1)["model"] is problem
    gone = weakref.ref(calculate)
    del calculate
    dispose(problem)
    assert gone() is None
    assert np.array_equal(block, np.full((128, 64), 17.0))
    assert vars(problem) == {}


def test_overlay_requires_exact_source_and_uses_live_patched_globals(tmp_path):
    source = tmp_path / "owned.py"
    source.write_text("value = 5\n\ndef routine(*, a=2):\n    return value + a\n")
    spec = importlib.util.spec_from_file_location("owned", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    changed = overlay(module.routine, digest, (("value + a", "value + a - 1", 1),))
    assert changed() == 6
    module.value = 10
    assert changed() == 11
    with pytest.raises(ValueError, match="unrecognized lifetime source"):
        overlay(module.routine, "0" * 64, ())
    with pytest.raises(ValueError, match="unrecognized lifetime anchor"):
        overlay(module.routine, digest, (("value + a", "value + a - 1", 2),))
