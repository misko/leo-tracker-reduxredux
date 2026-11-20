from types import SimpleNamespace

from tools.pipeline_eval.variants.coherent_peak_filter import FOLD_HZ, Peak
from tools.pipeline_eval.variants.epoch_tracks import links

RATE = 10_000_000
ORIGIN = 17_000_000_000_000


def config():
    return SimpleNamespace(
        alias_spacing_hz=FOLD_HZ,
        association_sigma=3,
        noise_sigma_hz=150,
        max_gap_s=10,
        max_slope_hz_s=8000,
    )


def observations():
    return [
        Peak(
            i,
            ORIGIN + i * RATE // 5,
            200 + 3000 * (i % 2) + i / 5,
            10_000 - 250 * i + (i % 3 - 1) * FOLD_HZ,
        )
        for i in range(24)
    ]


def test_timing_separates_two_sources_with_same_folded_cfo():
    chains, ambiguous = links(observations(), RATE, config())
    assert [chain.indices for chain in chains] == [list(range(0, 24, 2)), list(range(1, 24, 2))]
    assert ambiguous == 0
    assert all(
        abs((b - a) + 500) < 1e-7
        for chain in chains
        for a, b in zip(chain.frequencies[:-1], chain.frequencies[1:], strict=True)
    )


def test_raw_membership_uses_only_a_chronological_prefix():
    data = observations()
    full, _ = links(data, RATE, config())
    short, _ = links(data[:17], RATE, config())
    assert [c.indices for c in short] == [
        [i for i in c.indices if i < 17] for c in full if c.indices[0] < 17
    ]


def test_planted_fractional_timing_jump_is_rejected_with_same_cfo():
    data = observations()[::2]
    marker = data[6]
    data[6] = Peak(marker.visit, marker.counter, marker.epoch + 100, marker.cfo_hz)
    chains, _ = links(data, RATE, config())
    assert chains[0].indices == [i for i in range(len(data)) if i != 6]
    assert chains[1].indices == [6]
