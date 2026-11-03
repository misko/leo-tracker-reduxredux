from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_fractional_differential_phase import residualized_frequency_information, fractional_geometry


def test_complex_channel_elimination_matches_real_gaussian_schur_complement():
    rng = np.random.default_rng(81)
    x = rng.normal(size=(30, 5))+1j*rng.normal(size=(30, 5))
    d = rng.normal(size=(30, 2))+1j*rng.normal(size=(30, 2)); noise = 2.4
    xr = np.block([[x.real, -x.imag], [x.imag, x.real]])
    dr = np.vstack((d.real, d.imag)); residual = dr-xr@np.linalg.lstsq(xr, dr, rcond=None)[0]
    np.testing.assert_allclose(residualized_frequency_information(x, d, noise), 2*residual.T@residual/noise, rtol=1e-12)


def test_fractional_template_has_no_artificial_three_frame_placement_jump():
    fs = 2.5e6; samples = np.zeros(50000, complex)
    fit = dict(CFO_hz=0., offset_samples=0., modulation_ppm=0.)
    a = fractional_geometry(samples, fs, 'upper', 0., fit)
    # At equal fractional local frame time, every third frame repeats exactly.
    np.testing.assert_allclose(a['exact'][100:3000], a['exact'][10100:13000], rtol=1e-9, atol=1e-9)
