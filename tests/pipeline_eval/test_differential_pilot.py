import numpy as np
import pytest

from tools.pipeline_eval.qualification import differential_pilot_eval as study
from tools.pipeline_eval.variants import differential_pilot as dp


def test_three_true_frame_residues_and_two_sample_template_masks():
    for m, (residue, start) in enumerate(dp.STARTS, start=-1):
        assert 40_000 * m - 3 * start == dp.PHASE_THIRDS[residue]
    waves, active = dp.phase_templates("lower")
    product = dp.template_products("lower")
    assert not np.array_equal(waves[0], waves[1])
    assert not np.array_equal(waves[1], waves[2])
    for residue in range(3):
        expected = active[residue, : -dp.LAG] & active[residue, dp.LAG :]
        assert expected.sum() == 299 * dp.LAG
        assert np.all(product[residue, : -dp.LAG][~expected] == 0)
        assert np.all(product[residue, -dp.LAG :] == 0)


def test_fft_matches_direct_correlation_at_partial_and_full_epochs():
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL

    rng = np.random.default_rng(5)
    iq = rng.integers(-100, 100, (dp.SAMPLES, 2, 2), dtype="<i2")
    x = (iq[..., 0] + 1j * iq[..., 1]).T
    pairs = x[:, dp.LAG :] * x[:, : -dp.LAG].conj()
    pairs -= pairs.mean(axis=-1, keepdims=True)
    out = dp.surface(iq, "upper")
    kernels = [dp.template_products("upper", k) for k in (0, CONTROL_SYMBOL_ROLL)]
    for epoch in (0, 1, 8091, dp.FRAME - 1):
        expected = np.zeros(2)
        for k, ref in enumerate(kernels):
            value, energy = np.zeros(2, dtype=np.complex128), 0.0
            for residue, start in dp.STARTS:
                begin = epoch + start
                lo, hi = max(-begin, 0), min(dp.PAIR_COUNT - begin, dp.FRAME)
                if lo < hi:
                    admitted = ref[residue, lo:hi]
                    value += pairs[:, begin + lo : begin + hi] @ admitted.conj()
                    energy += np.vdot(admitted, admitted).real
            expected += (-1 if k else 1) * abs(value) ** 2 / energy
        assert out[:, epoch] == pytest.approx(expected, rel=5e-5, abs=5)


@pytest.mark.parametrize("edge", ("lower", "upper"))
@pytest.mark.parametrize("name", ("weak", "one-frame"))
def test_signed_cfo_and_one_live_frame_keep_true_epoch(edge, name):
    packet, target = study.synthetic(edge, name)
    rankings = dp.scout(packet, edge)
    assert [row[0][0] for row in rankings] == [target["epoch"]] * 2


def test_zero_and_other_receiver_independence():
    iq, target = study.synthetic("lower", "strong")
    iq[:, 0, :] = 0
    left, right = dp.scout(iq, "lower")
    assert left == ([], [])
    assert right[0][0] == target["epoch"]
