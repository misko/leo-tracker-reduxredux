import json
import multiprocessing
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.localization_v3.hierarchical import hierarchical_bound
from leo.analysis.localization_v4 import native_bound
from leo.analysis.localization_v4.backend import ProcessBound, validate_manifest


@pytest.fixture(scope="module")
def native_manifest(tmp_path_factory):
    folder = tmp_path_factory.mktemp("native-v4") / "build"
    environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                       MKL_NUM_THREADS="1")
    subprocess.run(
        [sys.executable, "-m", "leo.cli.algo07v4", "build-native", "--output", str(folder)],
        env=environment, check=True, capture_output=True, timeout=30,
    )
    return json.loads((folder / "manifest.json").read_bytes())


def sample():
    rng = np.random.default_rng(9871)
    groups = np.repeat(np.arange(3), 12)
    features = rng.normal(size=(36, 5))
    features[:, 2:] = 0
    for k in range(3):
        features[groups == k, 2 + k] = rng.normal(size=12)
    return rng.normal(size=36), features, np.linspace(1, 2, 36), groups


def equal(actual, expected):
    assert actual.keys() == expected.keys()
    for name in actual:
        np.testing.assert_allclose(actual[name], expected[name], rtol=2e-10, atol=2e-10,
                                   err_msg=name)


def test_real_native_activation_and_original_full_budget_agreement(native_manifest):
    backend = native_bound.NativeBound(native_manifest["binary"])
    values = sample()
    options = dict(prior_groups=np.array([-1, -1, 0, 1, 2]),
                   powers=np.array([1., .8, .7]), iterations=256)
    equal(backend(*values, **options), hierarchical_bound(*values, **options))
    equal(backend(*values, **options), hierarchical_bound(*values, **options))
    assert backend.counts["activated"] == 2 and backend.counts["cache_hits"] == 1
    assert backend.min_rcond == 1e-12


def test_unsupported_private_layout_falls_back_to_original(native_manifest):
    backend = native_bound.NativeBound(native_manifest["binary"])
    y, u, s, g = sample()
    g[:] = 0
    equal(backend(y, u, s, g), hierarchical_bound(y, u, s, g))
    assert backend.counts["fallback_unsupported"] == 1
    assert backend.counts["activated"] == 0


def test_conditioning_guard_falls_back_to_original(native_manifest):
    backend = native_bound.NativeBound(native_manifest["binary"])
    rng = np.random.default_rng(44)
    y = rng.normal(size=36)
    shared = rng.normal(size=36) * 1e5
    u = np.column_stack((shared, shared + rng.normal(size=36) * 1e-3))
    groups = np.repeat(np.arange(3), 12)
    actual = backend(y, u, 1., groups)
    expected = hierarchical_bound(y, u, 1., groups)
    for name in actual:
        np.testing.assert_array_equal(actual[name], expected[name])
    assert backend.min_rcond == 1e-12
    assert backend.counts["fallback_ill_conditioned"] == 1


@pytest.mark.parametrize("field", ["binary_sha256", "source_sha256", "wrapper_sha256",
                                  "flags", "original_sha256", "algorithm", "provider"])
def test_build_binding_rejects_changed_artifact_or_provider(native_manifest, field):
    changed = deepcopy(native_manifest)
    if field == "flags":
        changed[field] = ["-ffast-math"]
    elif field == "provider":
        changed[field]["threads"] = 2
    else:
        changed[field] = "changed"
    with pytest.raises(ValueError):
        validate_manifest(changed)


def test_loaded_provider_must_be_single_thread(native_manifest, monkeypatch):
    library, functions, info = native_bound.provider()
    changed = dict(info, threads=2)
    monkeypatch.setattr(native_bound, "provider", lambda: (library, functions, changed))
    with pytest.raises(ValueError, match="provider differs"):
        validate_manifest(native_manifest, check_provider=True)


def test_original_source_guard_rejects_changed_ast_boundary(monkeypatch):
    monkeypatch.setattr(native_bound, "ORIGINAL_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="hierarchical source"):
        native_bound._original_boundaries()


def test_fork_child_initializes_and_reports_actual_native_calls(native_manifest, tmp_path):
    bound = ProcessBound(native_manifest, tmp_path / "receipts")
    bound(*sample())
    parent = os.getpid()

    def run(send):
        equal(bound(*sample()), hierarchical_bound(*sample()))
        send.send(os.getpid())
        send.close()

    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=run, args=(send,))
    process.start()
    send.close()
    child = receive.recv()
    process.join(timeout=15)
    assert process.exitcode == 0
    receipts = bound.provenance()["receipts"]
    assert {r["pid"] for r in receipts} == {parent, child}
    assert all(r["counts"]["activated"] == 1 for r in receipts)
    assert all(r["counts"]["calls"] == 1 for r in receipts)
    assert Path(native_manifest["binary"]).is_file()
