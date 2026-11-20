from tools.pipeline_eval.qualification import ordinary_front_build, scout_radius_trace
from tools.pipeline_eval.variants import scout_radius, wide_regional


def test_radius_overlay_keeps_scout_abi_and_all_other_math():
    source = (ordinary_front_build.SOURCE / "native_glrt.c").read_text()
    wide = wide_regional.native_glrt(source)
    radius = scout_radius.overlay(wide)
    assert "wide&&context->receiver_count==2" in radius
    assert "context->refinement_mode==3 ? 2 : 1" in radius
    reverted = radius.replace("\n" + scout_radius.GATE, "").replace(
        "int first=current[c]-scout_radius,last=current[c]+scout_radius;",
        "int first=current[c]-1,last=current[c]+1;",
    )
    assert reverted == wide


def test_diagnostic_keeps_receiver_and_rank_order():
    evidence = """SCOUT_RADIUS_ROW
SCOUT_RADIUS_CELL 0 -800000 0x1.0p-4
SCOUT_RADIUS_PEAK 0 -800000 0x1.0p-4 1
SCOUT_RADIUS_KEEP 0 -800000 0x1.0p-4 1
SCOUT_RADIUS_ROW
SCOUT_RADIUS_CELL 13332 800000 0x0p+0
"""
    left, right = scout_radius_trace.trace_rows(evidence)
    assert left["kept"] == [[0, -800000, "0x1.0p-4", "1"]]
    assert right["cells"] == [[13332, 800000, "0x0p+0"]]
