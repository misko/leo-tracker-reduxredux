from itertools import pairwise

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_joint_blocks import (
    blocks,
    correction_error,
    primary_statistics,
    secondary_statistics,
)


def test_primary_block_dots_and_raw_covariance_do_not_identify_residual():
    p = np.array([1, 1, -1, -1], dtype=np.complex128)
    q = np.roll(p, 1)
    r = np.array([1, -1, 1, -1], dtype=np.complex128)
    block = slice(0, 4)
    x = np.array([p + r, q + r])
    y = np.array([p + q, q + r])
    np.testing.assert_array_equal(x.mean(axis=1), y.mean(axis=1))
    np.testing.assert_array_equal(x @ x.conj().T, y @ y.conj().T)

    models = [
        np.array(
            [
                primary_statistics(row, [(block, wave)])[0]
                for row, wave in zip(samples, (p, q), strict=True)
            ]
        )
        for samples in (x, y)
    ]
    np.testing.assert_array_equal(models[0], models[1])
    a, b = x - models[0], y - models[1]
    assert np.vdot(a[1], a[0]) == 4
    assert np.vdot(b[1], b[0]) == 0

    _, direction = primary_statistics(x[0], [(block, p)])
    for residual, energy in ((a[0], 0), (b[0], 4)):
        result = secondary_statistics(residual, np.zeros_like(p), direction, [block], [(block, q)])
        assert result["secondary_template_energy_retained"] == 0
        assert result["secondary_matched_energy_adc2"] == energy
    contained = secondary_statistics(a[0], np.zeros_like(p), direction, [block], [(block, p)])
    assert contained["secondary_template_energy_retained"] == 1


def test_signed_quantization_translation_requires_tie_and_clip_handling():
    raw = np.array([[10.0, 11.0], [-32768.0, 32767.0]])
    model = np.array([[0.5, 0.5], [1.8, -2.1]])
    residual = np.array([[10.0, 10.0], [-32768.0, 32767.0]])
    result = correction_error(raw, model, residual)
    assert result["modeled_residual_differing_components"] == 0
    assert result["half_integer_components"] == 2
    assert result["clipping_components"] == 2
    assert result["predicted_correction_differing_components"] == 3


def test_partial_block_coverage_and_fitted_shifted_pilot_indices():
    phases = np.arange(40_000)
    for epoch in (0.0, 40.0, 13_332 + 2 / 3):
        basis = list(blocks(epoch, phases))
        assert all(a.stop <= b.start for (a, _), (b, _) in pairwise(basis))
        for region, phase in basis:
            desired = (3 * np.arange(region.start, region.stop) - round(3 * epoch)) % 40_000
            np.testing.assert_array_equal(phase, desired)
            assert np.all((phase >= 264) & (phase < 39_864))
