import hashlib
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import compact_cavity_optimizer, v5_direct_cavity, v5_secant_fit


@pytest.mark.parametrize("target", ([1.4, -0.8], [8, 2], [0, 0]))
def test_direct_optimizer_matches_pinned_secant(target):
    def residual(x):
        u, v = x - target
        return np.array([0.1 * u**2 + u, 1.4 * v, u + v / 5])

    args = (residual, np.zeros(2), [-2, -3], [2, 4])
    expected = v5_secant_fit.bounded_secant(*args)
    actual = compact_cavity_optimizer.bounded_secant(*args)
    assert expected.keys() == actual.keys()
    np.testing.assert_array_equal(actual.pop("parameters"), expected.pop("parameters"))
    for got, want in zip(actual.pop("history"), expected.pop("history"), strict=True):
        np.testing.assert_array_equal(got["parameters"], want["parameters"])
        assert got["score"] == want["score"]
    assert expected == actual


def test_nomination_releases_only_the_model_after_last_read():
    model = SimpleNamespace(state=10, calculate=20, _fixed_phase_geometry_cache=30, labels=(0,))
    signed = {"base": model, "arms": {"c0": 123}}

    def nominate(context):
        assert context["base"].calculate == 20
        return {"record": context["base"].labels}

    assert v5_direct_cavity.nominal_families(signed, nominate) == {"record": (0,)}
    assert signed == {"arms": {"c0": 123}}
    assert vars(model) == {"labels": (0,)}


def test_nomination_failure_releases_model_and_propagates_original_error():
    context = {"base": SimpleNamespace(state=object())}

    def nominate(_context):
        raise RuntimeError("nomination test failure")

    with pytest.raises(RuntimeError, match="nomination test failure"):
        v5_direct_cavity.nominal_families(context, nominate)
    assert "base" not in context


def test_explicit_inputs_require_file_digest(tmp_path):
    path = tmp_path / "native.json"
    raw = b'{"source":{"session_id":"recording"}}'
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    assert v5_direct_cavity.verified_json(path, f"sha256:{digest}")["source"] == {
        "session_id": "recording"
    }
    path.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="declared SHA-256"):
        v5_direct_cavity.verified_json(path, digest)
