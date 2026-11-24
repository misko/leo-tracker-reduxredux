from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from portable_omitted_region import translated
from historical_orbit_publication import same_regional_path


def test_translation_wraps_longitude_for_both_centers_and_leaves_original_offer_intact():
    source = {"center": [3, 179], "screen_center": [4, 177], "width_km": 25}
    assert translated(source) == {"center": [3, -179], "screen_center": [4, 179], "width_km": 25}
    assert source == {"center": [3, 179], "screen_center": [4, 177], "width_km": 25}


def test_equivalent_science_requires_the_exterior_probe_and_same_projection_work():
    solve = {"geographic_projector": {"fallbacks": 0}, "prepared_exterior": {"catalogue_handoff": 1}}
    proof = {"reused": 0, "result": {"probes_evaluated": 24}, "cpu_s": 2}
    original = {"early_regional": [proof], "solve": solve}
    assert same_regional_path(dict(original, early_regional=[dict(proof, cpu_s=1)]), original)
    failed = dict(original, early_regional=[dict(proof, result={"diagnostic_error": "invalid orbit object"})])
    assert not same_regional_path(failed, original)
    assert not same_regional_path(failed, failed)
    assert not same_regional_path(dict(original, solve=dict(solve, geographic_projector={"fallbacks": 1})), original)
