from leo.presentation.fast_scan_orbits import render_fast_scan_orbits
from leo.presentation.orbit_plot import OrbitCurve, OrbitLane, OrbitPeak
from tools.pipeline_eval.variants.experimental.shared_orbit_figures import render_shared


def test_both_orbit_views_match_the_individual_pngs_including_empty_lanes():
    curves = (OrbitCurve("101", (0., 1., 2., 3.), (-500., 590., -590., float("nan"))),
              OrbitCurve("203", (0., 1., 2.), (20., 40., 60.)))
    peaks = (OrbitPeak("a", 1., 590., "101"), OrbitPeak("b", 1., 590., None),
             OrbitPeak("c", 2., 40., "203"))
    lanes = tuple(OrbitLane("RX1", f"CH{ch}", peaks if ch % 2 else (), curves) for ch in (1, 2, 5, 6))
    options = dict(title="Test · site (-27.12°, 108.8°)", alias_period_hz=1200., subtitle="Test receiver")
    individual = render_fast_scan_orbits(lanes, **options)
    assert render_shared(lanes, **options) == individual
