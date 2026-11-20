import os
import shutil
import subprocess
from pathlib import Path

from tools.pipeline_eval.qualification import ordinary_front_build
from tools.pipeline_eval.variants import scout_budget, wide_regional


def test_distinct_peaks_and_original_prefix(tmp_path):
    compiler = shutil.which("cc")
    assert compiler, "native component tests require a C compiler"
    source = Path(__file__).with_name("test_scout_budget_centers.c")
    target = tmp_path / "scout-centers"
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(scout_budget.HEADER.parent),
            str(source),
            "-o",
            str(target),
        ],
        check=True,
        env={**os.environ, "TMPDIR": str(tmp_path)},
    )
    subprocess.run([target], check=True)


def test_wide_fractional_scope_and_original_ordinary_fallback():
    source = (ordinary_front_build.SOURCE / "native_glrt.c").read_text()
    original = wide_regional.native_glrt(source)
    modified = scout_budget.native(original)
    assert "budget=wide&&context->refinement_mode==3 ? 16 : 4" in modified
    old_tracking = original.index("            count=leo_tracked_centers(")
    new_tracking = modified.index("            count=leo_tracked_centers(")
    old_limit, new_limit = (t.index("        if(count>") for t in (original, modified))
    assert original[old_tracking:old_limit] == modified[new_tracking:new_limit]
    original_selector = (ordinary_front_build.SOURCE / "kernel/private/proposal_core.c").read_text()
    candidate = scout_budget.proposal_core(original_selector)
    mark = "static int top4_linear("
    old_line, candidate_line = (
        s.split(mark, 1)[1].splitlines()[0] for s in (original_selector, candidate)
    )
    assert old_line == candidate_line
