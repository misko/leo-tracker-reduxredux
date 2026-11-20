from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.variants import nested_anchors as nested


def test_even_true_anchor_partition_is_frozen():
    assert nested.PRIMARY == (2, 30, 58, 86, 114, 142, 156, 184, 212, 240, 268, 296)
    assert len(nested.ADDITION) == 10
    assert set(nested.PRIMARY).isdisjoint(nested.ADDITION)
    assert tuple(sorted(nested.PRIMARY + nested.ADDITION)) == nested.SECOND


def test_partial_sums_preserve_actual_support_and_grid_values(tmp_path):
    binary, _ = nested.build(tmp_path)
    grid = nested.NestedGrid(binary)
    gen = np.random.default_rng(2026)
    packed = gen.integers(-4096, 4096, size=(42_000, 2))
    wave = packed[:, 0] + 1j * packed[:, 1]
    rate = 10_000_000
    template = acquisition.qin_edge_pilot_frame(rate, "lower")
    args = (
        acquisition,
        acquisition._folded_anchor_score_grid,
        wave,
        template,
        rate,
        (-130e3, 0, 130e3),
    )
    try:
        a, sa = grid._raw(*args, nested.PRIMARY, 13_333)
        b, sb = grid._raw(*args, nested.ADDITION, 13_333)
        f, sf = grid._raw(*args, nested.SECOND, 13_333)
        assert np.array_equal(sa + sb, sf)
        assert np.any(sf != sf[0])
        assert np.array_equal(
            np.asarray(grid.score_grid(*args, nested.SECOND, 13_333)),
            np.asarray(nested.divide(f, sf, out=np.zeros_like(f))),
        )
        sum_ = a + b
        got = np.asarray(nested.divide(sum_, sa + sb, out=sum_))
        expected = nested.divide(f, sf, out=f)
        assert np.allclose(got, expected, rtol=0, atol=8e-16)
    finally:
        grid.clear_cache()


@dataclass
class Settings:
    anchor_symbols: tuple[int, ...]


def test_window_scopes_nested_primary_and_preserves_retry(tmp_path):
    binary, _ = nested.build(tmp_path)
    grid = nested.NestedGrid(binary)
    seen = []

    def evaluate(probe, config, calibration, *, acquisition_config, **kwargs):
        seen.append(acquisition_config.anchor_symbols)
        return SimpleNamespace(has_fractional_detection=lambda gate: False)

    detector = SimpleNamespace(_evaluate_probe=evaluate)
    cfg = SimpleNamespace(glrt64_margin_gate=0.025)
    initial = tuple(range(2, 302, 26))
    with grid.window(detector, "reuse") as attempts:
        for anchors in (initial, nested.SECOND):
            detector._evaluate_probe(
                None,
                cfg,
                None,
                acquisition_config=Settings(anchors),
                receiver_id=1,
                probe_index=0,
                edge="lower",
            )
    assert attempts == [(1, 12, False), (1, 22, False)]
    assert seen == [nested.PRIMARY, nested.SECOND]
    assert not grid.partials
    assert detector._evaluate_probe is evaluate
