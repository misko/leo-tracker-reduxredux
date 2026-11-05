import numpy as np
import pytest
from compare_algo07v3_published import exact_persisted, mapped_predictive, read_export


def test_persisted_comparison_checks_every_scientific_value():
    old = dict(case="SCAN", phase=[1.0, 2.0], owners={"point": 69333}, score=1.0)
    new = dict(phase=np.array([1.0, 2.0]), owners={"point": 69333}, score=1.0)
    exact_persisted(old, new, {"case"})
    for changed in (
        dict(new, phase=np.array([1.0, 2.00000000001])),
        dict(new, owners={"point": 12345}),
        dict(new, score=1.000000000001),
    ):
        with pytest.raises(ValueError):
            exact_persisted(old, changed, {"case"})


def test_unknown_or_missing_bookkeeping_does_not_silently_disappear():
    with pytest.raises(ValueError, match="scope"):
        exact_persisted(dict(score=1, surprise=True), dict(score=1), set())
    with pytest.raises(ValueError, match="scope"):
        exact_persisted(dict(score=1), dict(score=1), {"case"})


def test_reference_export_hash_is_checked(tmp_path):
    import json

    stage = tmp_path / "ALGO02"
    stage.mkdir()
    (stage / "value.json").write_text('{"value": 1}')
    (stage / "descriptor.json").write_text(json.dumps(dict(files={"value.json": "wrong"})))
    with pytest.raises(ValueError, match="changed"):
        read_export(tmp_path, "ALGO02", "value.json")


def test_predictive_mapping_does_not_erase_unbound_retry_evidence(tmp_path):
    original = dict(
        selected=None,
        attempts=[
            dict(
                numerical_retry=dict(original_trial="/source/original", retry_trial="/source/retry")
            )
        ],
    )
    with pytest.raises(ValueError, match="no bound"):
        mapped_predictive(original, dict(source_worker_root="/source", files={}), tmp_path)


def test_failed_process_cannot_be_mapped_to_completed_science(tmp_path):
    original = dict(
        selected=None, attempts=[], stages=[dict(name="inventory", status="complete", returncode=1)]
    )
    with pytest.raises(ValueError, match="nonzero exit"):
        mapped_predictive(original, {}, tmp_path)


@pytest.mark.parametrize("width", [0, 3, 12])
@pytest.mark.parametrize("order", ["C", "F"])
def test_experimental_scatter_preserves_exact_assembly_across_sparse_shapes(width, order):
    import runpy
    from pathlib import Path

    from leo.analysis.localization_v3.hierarchical import hierarchical_bound

    path = (
        Path(__file__).resolve().parents[2] / "reports/2026_11_05_algo07v3_pair/probe_assembly.py"
    )
    candidate, _, _ = runpy.run_path(str(path))["candidate_function"]()
    rng = np.random.default_rng(177)
    features = rng.normal(size=(21, width))
    features[rng.random(features.shape) < 0.6] = 0
    features = np.array(features, order=order)
    y, sigma, groups = rng.normal(size=21), rng.uniform(10, 50, 21), np.arange(21) % 4
    prior = np.arange(width) // 3 - 1
    kwargs = dict(prior_groups=prior, powers=0.75, iterations=10)
    original = hierarchical_bound(y, features, sigma, groups, **kwargs)
    actual = candidate(y, features, sigma, groups, **kwargs)
    assert original.keys() == actual.keys()
    for key in original:
        a, b = np.asarray(original[key]), np.asarray(actual[key])
        assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), key
