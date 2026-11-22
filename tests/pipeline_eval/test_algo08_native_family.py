from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v4.native_bound import NativeBound, build
from tools.pipeline_eval.variants import algo08_native_family


def test_full_native_bound_with_families_and_structure_fallback(tmp_path):
    stock = build(tmp_path / "stock")
    library = tmp_path / "family.so"
    algo08_native_family.build(library)
    port = SimpleNamespace(NativeBound=NativeBound)
    rng = np.random.default_rng(47112)
    groups = np.repeat(np.arange(9), 24)
    raw = rng.normal(size=len(groups)) * 160
    sigma = rng.uniform(70, 120, len(groups))
    with algo08_native_family.measured_backend(port, library) as metrics:
        incumbent, candidate = NativeBound(stock), port.NativeBound(stock)
        for radio in (8, 9):
            design = np.zeros((len(raw), radio + 18))
            design[:, :radio] = rng.normal(size=(len(raw), radio))
            for group in range(9):
                rows = groups == group
                start = radio + 3 * (group // 3)
                design[rows, start : start + 3] = rng.normal(size=(int(rows.sum()), 3))
                design[rows, radio + 9 + group] = 1.
            prior = np.full(design.shape[1], -1)
            prior[radio:radio + 9:3] = np.arange(3)
            for u in (design, design + rng.normal(size=design.shape) * 1e-4):
                old = incumbent(raw, u, sigma, groups, prior_groups=prior)
                new = candidate(raw, u, sigma, groups, prior_groups=prior)
                for key in old:
                    np.testing.assert_allclose(new[key], old[key], atol=1e-9, rtol=1e-9,
                                               err_msg=key)
        incumbent.clear()
    assert metrics["kernel_calls"] == 4
    assert metrics["family_attempts"] >= metrics["family_activated"] > 0
    assert metrics["original_width_sum"] > 1.7 * metrics["radio_width_sum"]
