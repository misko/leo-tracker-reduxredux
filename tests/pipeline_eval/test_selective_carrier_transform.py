from cmath import exp, pi
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from selective_carrier_transform import eligible_bins, layout, old_screen


@pytest.mark.parametrize("center", [-4_200_000., -214_983.123, 0., 182_451.015625, 4_200_000.])
def test_current_signed_band_covers_every_inner_residue(center):
    selected = eligible_bins(4096, 2_500_000, center, 800_000.)
    assert selected == list(range(1311)) + list(range(2786, 4096))
    actual = layout(selected, 4096, 128)
    assert actual["requested_residues"] == 128
    assert actual["wanted_outer_outputs_per_residue"] == {20: 67, 21: 61}
    radix2 = layout(selected, 4096, 2048)
    assert radix2["requested_residues"] == 2048
    assert radix2["unused_output_bins"] == 1475


def test_queried_bins_and_energy_cannot_certify_the_hidden_winner():
    spectra = [[abs(sum(v*exp(-2j*pi*k*t/8) for t,v in enumerate(signal)))**2 for k in range(8)]
               for signal in ((1+1j, 0, -1j), (1-1j, 0, 1j))]
    assert [spectra[0][k] for k in (0, 4)] == pytest.approx([spectra[1][k] for k in (0, 4)])
    assert sum(spectra[0]) == pytest.approx(sum(spectra[1]))
    assert spectra[0][1] < spectra[0][3] and spectra[1][1] > spectra[1][3]


def test_known_full_detector_coarse_bound_has_expensive_fallback():
    evidence = old_screen()
    assert sum(row["omitted_rows"] for row in evidence.values()) == 170
    assert sum(row["original_rows"] for row in evidence.values()) == 1968
    assert all(row["rows_1024_omitted"] == 0 and row["bound_violations"] == 0
               and row["best_independent_coarse_plus_fallback_cost_ratio"] > 1.2
               for row in evidence.values())
