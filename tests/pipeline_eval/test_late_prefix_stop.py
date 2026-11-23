from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))
from late_prefix_stop import RECIPE_SHA, native_budget, native_signature, project, verification_budget
from late_prefix_stop_score import has_complete_evidence, passes


def packet():
    probes = [dict(visit_index=visit, channel=1, actual_rf_hz=12e9, edge="lower", receiver_id=receiver,
                   valid_start_counter=200000*visit, payload_start_sample=200000*visit,
                   candidates=[dict(id=visit)])
              for visit in range(16) if visit != 1 for receiver in (0, 1)]
    source = dict(qualified=True, sample_rate_hz=10_000_000, raw_recording_authority_digest="sha256:raw", probes=probes)
    detector = "sha256:" + RECIPE_SHA
    source["analysis_manifest_sha256"] = native_signature(source, detector, probes)
    return dict(source=source, clock_anchor=dict(sample_counter=0), delivery_clocks=list(range(16)),
                provenance=dict(detector_sha256=detector, scope="cancellation", window_count=16,
                                processed_windows=15, excluded_windows=[dict(visit=1)], run_id="source"))


@pytest.mark.parametrize(("mode", "cut", "kept_full", "kept_short"),
                         [("half", 8, 2, 12), ("three-quarters", 12, 4, 18)])
def test_stop_keeps_all_authorities_and_counts_only_valid_stereo_calls(mode, cut, kept_full, kept_short):
    original = packet()
    projected, mask = project(original, mode)
    assert mask["issued_prefix"] == cut
    assert mask["opportunity_rows"] == 30
    assert mask["kept_native_lanes"] == {"full": kept_full, "short_primary": kept_short}
    for before, after in zip(original["source"]["probes"], projected["source"]["probes"], strict=True):
        assert after == (before if before["visit_index"] < cut else dict(before, candidates=[]))
        assert before["candidates"]
    for key in ("clock_anchor", "delivery_clocks"):
        assert projected[key] == original[key]
    for key in ("detector_sha256", "excluded_windows", "window_count"):
        assert projected["provenance"][key] == original["provenance"][key]
    assert projected["source"]["raw_recording_authority_digest"] == original["source"]["raw_recording_authority_digest"]
    assert projected["source"]["analysis_manifest_sha256"] != original["source"]["analysis_manifest_sha256"]


def test_acquisition_estimate_keeps_every_nonnative_second():
    _, mask = project(packet(), "half")
    audit = dict(native=dict(native_calls=dict(full=4, short_primary=26),
                             native_cpu_ns=dict(full=4000, short_primary=2600)),
                 acquire=dict(cpu_ns=16_600))
    cost = native_budget(audit, mask)
    assert cost["estimated_omitted_native_cpu_s"] == pytest.approx(3400e-9)
    assert cost["fixed_nonnative_acquisition_cpu_s"] == pytest.approx(10_000e-9)
    assert cost["modeled_total_acquisition_cpu_s"] == pytest.approx(13_200e-9)


def test_suffix_cover_keeps_every_byte_in_the_cutoff_straddling_member():
    rows = [dict(stop=8, compressed=2, decoded=4, index=1), dict(stop=11, compressed=3, decoded=5, index=1)]
    budget = verification_budget(rows, 6)
    assert budget["suffix_intersecting_members"] == 2
    assert budget["suffix_intersecting_bytes"] == budget["all_bytes"]


def test_quality_gate_checks_both_arms_and_both_baselines():
    good = dict(error_km=1., versus={"full": {"error_delta_km": .25}, "named": {"error_delta_km": 0.}})
    bad = dict(error_km=1., versus={"full": {"error_delta_km": .251}, "named": {"error_delta_km": 0.}})
    assert passes(dict(c0=good, fitted_c=good), True)
    assert not passes(dict(c0=good, fitted_c=bad), True)
    assert not passes(dict(c0=good, fitted_c=good), False)


def test_installed_success_terminal_requires_complete_grid_and_figures():
    images = dict(images=[None]*8)
    assert has_complete_evidence(dict(decision="ok"), dict(grid_complete=True), images)
    assert not has_complete_evidence(dict(decision="ok"), dict(grid_complete=False), images)
    assert not has_complete_evidence(dict(decision="withheld"), dict(grid_complete=True), images)
