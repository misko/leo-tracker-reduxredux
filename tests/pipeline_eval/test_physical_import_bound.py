import pytest

from reports.ALGO08.v3.physical_import_bound import ACTIVE_PHASE, ceiling, guarded, imports, overlap


def test_even_a_free_tiny_request_can_leave_a_summed_gap():
    bound = ceiling(6.55, .54, 12.24)
    assert bound["needed_s"] == pytest.approx(.97)
    assert bound["even_zero_tiny_shortfall_s"] == pytest.approx(.43)
    assert bound["even_zero_tiny_speedup"] == pytest.approx(12.24/6.55)


def test_import_overlap_excludes_active_only_and_nested_totals():
    a = imports("import time: 10 | 40 |   seen\nimport time: 6 | 46 | tiny\n")
    b = imports(f"import time: 11 | 38 | seen\n{ACTIVE_PHASE}\nimport time: 60 | 70 | scipy\n")
    row = overlap(a, b)
    assert row["count"] == 1
    assert row["measured_common_s"] == [10e-6, 11e-6]
    assert row["active_only_s"] == 60e-6


def test_import_probe_guard_rejects_input_metadata_and_waveforms(tmp_path):
    instruction = guarded(tmp_path)
    instruction("open", (str(tmp_path/"libraries.json"),))
    for file in (tmp_path/"recording"/"manifest.json", tmp_path/"causal"/"snapshot.json",
                 tmp_path/"unread-offer.json", tmp_path/"foreign.ci16.zst", "/srv/bulk/example", "/mnt/qnap01/example"):
        with pytest.raises(ValueError, match="never read a request"):
            instruction("open", (str(file),))
