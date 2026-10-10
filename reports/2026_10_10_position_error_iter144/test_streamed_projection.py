import numpy as np
import pytest
from projection import decompose
from streamed_projection import decompose_streamed, streamed_decompose


def compare(delta, spatial, nuisance, weights, *, energy_rtol=2e-11, **kwargs):
    dense = decompose(delta, spatial, nuisance, weights, **kwargs)
    for chunk in (1, 3, 17, 4096):
        result = streamed_decompose(delta, spatial, nuisance, weights, chunk_rows=chunk, **kwargs)
        for key in (
            "total_weighted_energy",
            "nuisance_energy",
            "spatial_conditional_energy",
            "outside_energy",
            "unweighted_rms_hz",
        ):
            assert result[key] == pytest.approx(dense[key], rel=energy_rtol, abs=2e-22)
        for span in ("nuisance_span", "combined_span"):
            assert result[span]["rank"] == dense[span]["rank"]
            assert result[span]["nonzero_columns"] == dense[span]["nonzero_columns"]
            np.testing.assert_allclose(
                result[span]["singular_values"],
                dense[span]["singular_values"],
                rtol=2e-11,
                atol=2e-14,
            )
        for key in ("original_row_count", "retained_rows", "positive_weight_rows", "rtol"):
            assert result[key] == dense[key]
        assert result["compression"]["factor_rows"] <= nuisance.shape[1] + 3
    return dense


def test_random_full_rank_fragmentation_and_nonuniform_weights():
    rng = np.random.default_rng(144)
    n = 173
    compare(
        rng.normal(size=n),
        rng.normal(size=(n, 2)),
        rng.normal(size=(n, 7)),
        rng.uniform(0.01, 3, n),
        original_row_count=10000,
    )


def test_rank_deficiency_and_confounded_spatial():
    rng = np.random.default_rng(5)
    z = rng.normal(size=(79, 2))
    nuisance = np.column_stack((z, z[:, 0] * 3, np.zeros(79)))
    spatial = np.column_stack((z[:, 0], z[:, 1]))
    result = compare(z @ [2, -1], spatial, nuisance, np.ones(79))
    assert result["nuisance_span"]["rank"] == result["combined_span"]["rank"] == 2
    assert result["outside_energy"] < 1e-24
    assert result["spatial_conditional_energy"] < 1e-24


@pytest.mark.parametrize("epsilon", [1e-7, 1e-14])
def test_ill_conditioned_modes_above_and_below_fixed_tolerance(epsilon):
    rng = np.random.default_rng(8)
    base = rng.normal(size=97)
    nuisance = np.column_stack((base, base + epsilon * rng.normal(size=97)))
    # The retained 1e-7 singular mode amplifies backward rounding errors by ~1e7.
    # Ranks/singular values still use the tight comparison; only projected energies
    # use a documented condition-aware bound, rather than claiming bitwise parity.
    compare(
        rng.normal(size=97),
        rng.normal(size=(97, 2)),
        nuisance,
        np.ones(97),
        rtol=1e-10,
        energy_rtol=1e-7 if epsilon == 1e-7 else 2e-11,
    )


def test_zero_weight_rows_missing_rows_and_column_unit_changes():
    rng = np.random.default_rng(18)
    n = 53
    delta, spatial, nuisance = rng.normal(size=n), rng.normal(size=(n, 2)), rng.normal(size=(n, 3))
    weights = np.ones(n)
    weights[::3] = 0
    first = compare(delta, spatial, nuisance, weights, original_row_count=100000)
    scaled = compare(
        delta,
        spatial * [1e-120, -1e120],
        nuisance * [1e-150, -1e150, 1e-25],
        weights,
        original_row_count=100000,
    )
    assert first["rtol"] == np.finfo(float).eps * 100000
    for key in ("nuisance_energy", "spatial_conditional_energy", "outside_energy"):
        assert scaled[key] == pytest.approx(first[key], rel=1e-12, abs=1e-20)
    # Physically rescale Hz and its precision together: weighted energies are unchanged.
    hz = streamed_decompose(delta * 1000, spatial, nuisance, weights / 1e6)
    assert hz["total_weighted_energy"] == pytest.approx(first["total_weighted_energy"])
    assert hz["unweighted_rms_hz"] == pytest.approx(first["unweighted_rms_hz"] * 1000)


def test_all_zero_weights_and_no_nuisance_columns():
    result = compare(np.arange(1, 8), np.ones((7, 2)), np.zeros((7, 0)), np.zeros(7))
    assert result["total_weighted_energy"] == result["outside_energy"] == 0
    assert result["combined_span"]["rank"] == 0
    compare(
        np.arange(1, 8), np.column_stack((np.arange(7), np.ones(7))), np.zeros((7, 0)), np.ones(7)
    )


def test_factory_with_empty_blocks_and_known_orthogonal_energy():
    basis = np.eye(4)

    def blocks():
        yield np.empty(0), np.empty((0, 2)), np.empty((0, 1)), np.empty(0)
        for i in range(4):
            yield (
                np.array([2, 3, 4, 5])[i : i + 1],
                basis[i : i + 1, 1:3],
                basis[i : i + 1, :1],
                np.ones(1),
            )

    result = decompose_streamed(blocks, nuisance_columns=1, original_row_count=1000)
    assert result["nuisance_energy"] == pytest.approx(4)
    assert result["spatial_conditional_energy"] == pytest.approx(25)
    assert result["outside_energy"] == pytest.approx(25)
    assert result["compression"]["blocks"] == 4


def test_validation_matches_dense_and_detects_nonrepeatable_row_count():
    with pytest.raises(ValueError, match="Original"):
        streamed_decompose([1, 2], np.eye(2), np.zeros((2, 0)), [1, 1], original_row_count=1)
    with pytest.raises(ValueError, match="Finite"):
        streamed_decompose([1, 2], np.eye(2), np.zeros((2, 0)), [1, -1])
    with pytest.raises(ValueError, match="chunk"):
        streamed_decompose([1], [[1, 2]], np.zeros((1, 0)), [1], chunk_rows=True)
    with pytest.raises(ValueError, match="nonempty"):
        decompose_streamed(lambda: iter(()), nuisance_columns=1, original_row_count=10)
    calls = 0

    def unstable():
        nonlocal calls
        calls += 1
        n = 2 if calls == 1 else 1
        yield np.ones(n), np.ones((n, 2)), np.zeros((n, 0)), np.ones(n)

    with pytest.raises(ValueError, match="changed rows"):
        decompose_streamed(unstable, nuisance_columns=0, original_row_count=10)


def test_linear_algebra_only_receives_bounded_blocks_and_small_factors(monkeypatch):
    rng = np.random.default_rng(33)
    n, p, chunk = 211, 5, 11
    shapes = []
    qr, svd = np.linalg.qr, np.linalg.svd

    def tracked_qr(a, *args, **kwargs):
        shapes.append(("qr", a.shape))
        return qr(a, *args, **kwargs)

    def tracked_svd(a, *args, **kwargs):
        shapes.append(("svd", a.shape))
        return svd(a, *args, **kwargs)

    monkeypatch.setattr(np.linalg, "qr", tracked_qr)
    monkeypatch.setattr(np.linalg, "svd", tracked_svd)
    result = streamed_decompose(
        rng.normal(size=n),
        rng.normal(size=(n, 2)),
        rng.normal(size=(n, p)),
        np.ones(n),
        chunk_rows=chunk,
    )
    assert result["retained_rows"] == n
    assert all(
        rows <= chunk + p + 3 and columns <= p + 3
        for kind, (rows, columns) in shapes
        if kind == "qr"
    )
    assert all(
        rows <= p + 3 and columns <= p + 2 for kind, (rows, columns) in shapes if kind == "svd"
    )
