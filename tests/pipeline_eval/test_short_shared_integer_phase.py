import cmath
import json

import pytest

from reports.ALGO08.v3 import short_shared_integer_phase as experiment
from reports.ALGO08.v3.sparse8_native_profile import Factor


@pytest.mark.parametrize("cfo", (-799_100., 105_700., 789_250.))
def test_relative_integer_rotation_has_same_fractional_frame_power(cfo):
    scale = -2*cmath.pi*cfo/10_000_000
    values = [1.25+3j, 2.75-19j, -4.75+9j, 12.5+4.25j]
    for start in (0, 13333, 53333):
        for offset in (-1.75, .125, 2.25):
            absolute = sum(v*cmath.exp(1j*scale*(start+88+k+offset)) for k, v in enumerate(values))
            integer_table = sum(v*cmath.exp(1j*scale*(88+k)) for k, v in enumerate(values))
            assert abs(absolute)**2 == pytest.approx(abs(integer_table)**2, rel=2e-11)


def test_stage_compare_retains_signed_zero_and_rejects_missing_factors():
    exact = (0, 2, 0., -1000., .2, .02)
    assert experiment.compare(exact, (*exact[:4], .2+1e-10, .02), 4)[0] == pytest.approx(1e-10)
    with pytest.raises(ValueError, match="Discrete"):
        experiment.compare(exact, (0, 2, -0., *exact[3:]), 4)
    with pytest.raises(ValueError, match="Discrete"):
        experiment.compare(exact, (), 4)
    with pytest.raises(ValueError, match="continuous"):
        experiment.compare(exact, (*exact[:4], .201, .02), 4)
    assert experiment.native_bytes(exact, Factor) == bytes(Factor(*exact))


def test_native_overlay_keeps_exact_signed_table_guard_and_invalidation():
    source = """static int phase_free_fractional(
    ++phase_attempts;
        PortableFineComplex p = rotate(-tau * cfo * (first + k + offset) / rate);
        exact[k] = (GlrtComplex){a.re * p.r - a.im * p.i, a.re * p.i + a.im * p.r};
        control[k] = (GlrtComplex){b.re * p.r - b.im * p.i, b.re * p.i + b.im * p.r};
    double roundoff = 128. * DBL_EPSILON;
    if (!(egap > 2. * er && cgap > 2. * cr &&
          fabs(margin - gate) > radius && fabs(margin - .1) > radius)) return 0;
    ++phase_accepted;
"""
    derived = experiment.share_table(source)
    assert "w->integer_hz != cfo || fegetround() != FE_TONEAREST" in derived
    assert "GlrtComplex p = w->glrt_rotation[k]" in derived
    assert "w->integer_hz = NAN;" in derived
    assert "256. * DBL_EPSILON" in derived
    assert "fabs(margin - gate) > radius && fabs(margin - .1) > radius" in derived


def test_sealed_callback_receipt_preserves_order_and_prices_unchanged_anchors():
    path = experiment.HERE / "measurements" / "short-shared-integer-phase.json"
    receipt = json.loads(path.read_bytes())
    watch = receipt["watch"]
    data = watch["result"]
    assert watch["returncode"] == 0 and watch["attempts"] == 1
    assert data["build"]["binaries"]["installed"] == experiment.ORIGINAL
    assert data["backing_waveform_reads"] == data["catalogue_reads"] == data["solves"] == 0
    for case, expected in (("DS30-0163", (36, 10, 20, 17)), ("DS30-0419", (6, 4, 5, 5))):
        rows = data["panels"][case]
        keys = [(row["visit"], row["rx"]) for row in rows]
        assert keys == sorted(set(keys))
        positives = verified = shortcuts = 0
        for row in rows:
            assert len(row["rounds"]) == experiment.REPEATS
            positives += bool(row["original"])
            verified += bool(row["rounds"][0]["exact"][1])
            shortcuts += row["rounds"][0]["shared"][2][1]
            for pair in row["rounds"]:
                exact, shared = (pair[arm] for arm in experiment.ARMS)
                assert experiment.native_bytes(exact[0], Factor) == experiment.native_bytes(row["original"], Factor)
                experiment.compare(exact[0], shared[0], 4)
                experiment.compare(exact[1], shared[1], 5)
                assert shared[2] == row["rounds"][0]["shared"][2]
                if not shared[2][1]:
                    assert exact[:2] == shared[:2]
        assert (len(rows), positives, verified, shortcuts) == expected
    price = experiment.price(data)
    assert receipt["field_price"] == price
    assert price["cohort"] == {"positive": 432, "empty": 808}
    assert price["estimate_by_donor"]["DS30-0163"]["projected_saved_cpu_s"] == pytest.approx(0.0892312532923)
