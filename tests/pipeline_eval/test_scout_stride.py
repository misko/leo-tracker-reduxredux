import os
import shutil
import subprocess
from pathlib import Path

from tools.pipeline_eval.qualification import ordinary_front_build
from tools.pipeline_eval.variants import scout_stride, wide_regional


def test_even_cell_math_and_physical_neighbor_choices(tmp_path):
    cc = shutil.which("cc")
    assert cc, "native component tests require a C compiler"
    source = Path(__file__).with_name("test_scout_stride_coarse.c")
    output = tmp_path / "test-stride-coarse"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-O3",
            "-fno-fast-math",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(scout_stride.HEADER.parent),
            str(source),
            "-o",
            str(output),
            "-lm",
        ],
        env={**os.environ, "TMPDIR": str(tmp_path)},
        check=True,
    )
    subprocess.run([output], check=True)


def test_stride_activation_leaves_rank_fine_and_fallback_release_intact():
    source = ordinary_front_build.SOURCE
    native = wide_regional.native_glrt((source / "native_glrt.c").read_text())
    modified = scout_stride.native(native)
    guard = "        context->search->scout_stride=wide && context->receiver_count==2 &&\n"
    limits = "            context->refinement_mode==3 && context->search->regional_count<=12;\n"
    assert guard + limits in modified
    assert modified.replace(guard + limits, "") == native
    coarse = wide_regional.coarse(
        (source / "kernel/private/native_presence/coarse_fp32.h").read_text()
    )
    modified = scout_stride.coarse(coarse)
    assert "else if (w->wide_regional) wide_regional_float_add" in modified
    assert "else coarse_float_add(samples,real,imag,taps,inverse,sum);" in modified
