import shutil
import subprocess
from pathlib import Path

from tools.pipeline_eval.qualification import coarse_glrt_build


def test_triplet_arithmetic_matches_stock_cell_accumulation(tmp_path):
    compiler = shutil.which("cc")
    assert compiler, "native component tests require a C compiler"
    source = coarse_glrt_build.stock.SOURCE / "kernel/private/native_presence/coarse_fp32.h"
    stock = source.read_text().split("static void coarse_fp32_templates", 1)[0]
    (tmp_path / "stock_coarse.h").write_text(stock + "\n#pragma GCC pop_options\n")
    target = tmp_path / "coarse-triplet"
    test = Path(__file__).with_name("coarse_glrt_triplet.c")
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-O3",
            "-fno-fast-math",
            "-fcx-limited-range",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(tmp_path),
            "-I",
            str(coarse_glrt_build.HEADER.parent),
            str(test),
            "-o",
            str(target),
            "-lm",
        ],
        check=True,
    )
    subprocess.run([target], check=True)


def test_overlay_leaves_native_support_boundaries_and_scalar_residual_path():
    path = coarse_glrt_build.stock.SOURCE / "kernel/private/native_presence/coarse_fp32.h"
    stock = path.read_text()
    triplet = coarse_glrt_build.overlay(stock)
    fallback = "ptrdiff_t position=base+epoch;"
    assert stock[stock.index(fallback) :] == triplet[triplet.index(fallback) :]
    assert "epoch+2<valid" in triplet
    assert "w->regional_epochs[active+2]==epoch+2" in triplet
