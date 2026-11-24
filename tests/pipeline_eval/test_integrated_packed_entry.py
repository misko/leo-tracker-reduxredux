import gzip
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import integrated_packed_member as member
from reports.ALGO08.v3 import legacy_block_raw_entry as legacy
from reports.ALGO08.v3.integrated_packed_entry import require_prepared_payload
from reports.ALGO08.v3.integrated_packed_full import command, reverse_required
from reports.ALGO08.v3.integrated_packed_cost import MEASURES, metrics, replace_acquisition, score


def test_packed_selection_reuses_scientific_flags_without_original_acquisition_modes():
    flags = [("--recording", "/prior"), ("--output", "/output"), ("--legacy-first-map-history", "/history.so"),
             ("--legacy-first-map-history-sha256", "pin"), ("--legacy-first-map-fast", "/solver-roster")]
    book = {"source": "/signed", "options": [x for pair in flags for x in pair] +
            ["--cairo-six-sheets", "--sparse8-primary", "--verify-original-once"]}
    old = member.arguments(book, "ordinary", Path("/ordinary"))
    new = member.arguments(book, "packed", Path("/packed"))
    assert "--verify-original-once" in old and "--strict-packed-eight" not in old
    assert "--verify-original-once" not in new and "--legacy-first-map-history" not in new
    assert "--strict-packed-eight" in new
    for key in ("--legacy-first-map-fast", "--sparse8-primary", "--cairo-six-sheets", "/signed"):
        assert key in old and key in new


def test_original_port_rejects_strict_and_mixed_input_modes():
    args = SimpleNamespace(history_risk_route=True, portable_orbit_index="/orbit", visit_frame_custody=None,
                           strict_packed_eight=True, cairo_residual_layout=False, cairo_six_sheets=True,
                           legacy_map_custody="/old-map", legacy_map_custody_sha256=None,
                           legacy_map_library=None, legacy_map_library_sha256=None)
    with pytest.raises(ValueError, match="original recording"):
        legacy.run(args, allow_cairo_orbits=True)
    with pytest.raises(ValueError, match="cannot use original block replay"):
        legacy.run(args, allow_cairo_orbits=True, allow_strict_packed=True)


def test_cost_replaces_acquisition_once_and_charges_prepared_setup():
    assert replace_acquisition(7., 3., 2., .1) == pytest.approx(6.1)
    with pytest.raises(ValueError):
        replace_acquisition(7., 8., 2., .1)


def test_sealed_cost_ledger_keeps_prepare_retrofit_and_owned_writer_distinct():
    result = score()
    row = result["modeled_integrated"]["positive_first"]
    ready = row["prepared_projection_positive_only"]
    conversion = result["historical_strict"]["conversion_and_readback_s"][0]
    assert row["existing_first_use_positive"]["summed_s"] == pytest.approx(ready["summed_s"] + conversion)
    writer = result["owned_0016"]["packed"]
    assert row["owned_write_to_exit_positive_projection"]["candidate_s"] == pytest.approx(
        ready["summed_s"] - row["observed_processes_s"][1] + writer["write_s"] + writer["independent_readback_s"])
    assert ready["remaining_to_half_s"] > 0


def test_complete_prepared_launch_preserves_offer_and_uses_strict_custody():
    original = ["--recording", "/signed-original", "--output", "/old", "--region", "/offer",
                "--legacy-first-map-history", "/legacy-lib", "--legacy-first-map-history-sha256", "old-pin",
                "--verify-original-once", "--sparse8-primary", "--cairo-six-sheets"]
    packed = command(original, Path("/next"), {"map": "/new/map", "map_sha256": "new-pin", "codec": "/codec"},
                     Path("/release"))
    assert packed[:5] == ["/usr/bin/timeout", "--kill-after=2s", "75s", "/release/venv/bin/python", "-IB"]
    assert not any(x in packed for x in ("--verify-original-once", "/legacy-lib", "old-pin"))
    assert {"/signed-original", "/offer", "/next", "--sparse8-primary", "--cairo-six-sheets",
            "--strict-packed-eight", "/new/map", "new-pin", "/codec"} <= set(packed)


def test_prepared_waveform_guard_and_reversal_threshold():
    for path in ("/original/0.ci16.zst", b"0.ci16.zst"):
        with pytest.raises(PermissionError, match="original encoded"):
            require_prepared_payload("open", (path, "r", 0))
    for path in ("/derivative/prefix.ci16p", "/original/manifest.json", 23):
        require_prepared_payload("open", (path, "r", 0))
    assert reverse_required(dict(summed_speedup=1.9, paired_median_speedup=1.9))
    assert not reverse_required(dict(summed_speedup=1.89, paired_median_speedup=2.))
    assert not reverse_required(dict(summed_speedup=2., paired_median_speedup=1.89))


def test_sealed_complete_pair_charges_source_once_and_recomputes_threshold():
    content = (MEASURES / "integrated-packed-full.json.gz").read_bytes()
    assert sha256(content).hexdigest() == "de21badbdc5c310748401bad3ca485463c49d633e016b4317b87f7ac9c5287be"
    receipt = json.loads(gzip.decompress(content))
    pair = receipt["pair"]["document"]
    assert pair["cases"] == pair["order"] == ["DS30-0016", "DS30-0107"]
    for case, records in receipt["cases"].items():
        assert records["result"]["source_sha256"] == pair["case_result_sha256"][case]
        assert records["result"]["document"]["qualified"]
        observed = records["clock"]["document"]["clock"]
        source = records["admission"]["document"]["source_check"]
        for key in ("elapsed_s", "cpu_s"):
            assert pair["paid"][case][key] == pytest.approx(observed[key] + source[key])
    ready = metrics([row["elapsed_s"] for row in pair["fresh_stock"]],
                    [pair["paid"][case]["elapsed_s"] for case in pair["cases"]])
    assert ready == pair["prepared"]
    assert ready["paired_median_speedup"] > 2
    assert pair["reverse_warranted"] is reverse_required(ready) is False
