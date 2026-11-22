from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v4.native_bound import NativeBound, build
from tools.pipeline_eval.variants import algo08_fixed_gram as variant


def test_fixed_numeric_gram_reuses_only_identical_columns_and_noise(tmp_path):
    stock = build(tmp_path / "stock")
    library = tmp_path / "fixed.so"
    variant.build(library)
    port = SimpleNamespace(NativeBound=NativeBound)
    rng = np.random.default_rng(2026)
    groups = np.repeat(np.arange(4), [24, 38, 32, 39])
    noise = rng.uniform(40., 120., len(groups))
    y = noise * rng.normal(size=len(groups))
    features = np.column_stack((rng.normal(size=(len(groups), 7)), np.eye(4)[groups] * 1000))
    altered = features.copy()
    altered[:, 3:5] *= -0.4
    changed_noise = noise.copy()
    changed_noise[12] = np.nextafter(noise[12], np.inf)
    keep = np.arange(len(y)) != 5
    powers = np.array([1., 0.4, 0.6, 0.2])
    calls = [
        (y, features, noise, groups),
        (y + 17., features, noise, groups),
        (y, altered, noise, groups),
        (y, altered, changed_noise, groups),
        (y[keep], altered[keep], changed_noise[keep], groups[keep]),
        (y, altered, noise, groups),
        (y, np.full((len(y), 1), 2.**108), noise, groups),
    ]

    def run(mode):
        with variant.measured_backend(port, library, mode=mode) as counts:
            bound = port.NativeBound(stock)
            output = []
            for observed, design, sigma, owner in calls:
                prior = np.full(design.shape[1], -1)
                prior[:3] = 0
                output.append(bound(observed, design, sigma, owner, powers=powers,
                                    prior_groups=prior))
        return counts, output

    _, expected = run("control")
    counts, actual = run("fixed")
    mapped_counts, mapped = run("mapped")
    for output in (actual, mapped):
        for reference, candidate in zip(expected, output, strict=True):
            assert candidate.keys() == reference.keys()
            for key in reference:
                assert np.asarray(candidate[key]).tobytes() == np.asarray(reference[key]).tobytes(), key
    assert port.NativeBound is NativeBound
    assert counts["gram_cold"] == 2
    assert counts["gram_reused"] == 4
    assert counts["gram_fallback"] == 1
    assert counts["activated"] == 7
    assert counts["replayed_products"] < counts["original_products"]
    assert mapped_counts["assembly_mapped"] == mapped_counts["assembly_calls"] > 0
