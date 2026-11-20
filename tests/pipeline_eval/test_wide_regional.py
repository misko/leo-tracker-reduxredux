import os
import shutil
import subprocess
from pathlib import Path

from tools.pipeline_eval.qualification import ordinary_front_build
from tools.pipeline_eval.variants import wide_regional


def test_wide_finite_float_accumulation_and_padded_stride(tmp_path):
    cc = shutil.which("cc")
    assert cc, "native component tests require a C compiler"
    source = Path(__file__).with_name("wide_regional_cells.c")
    test = tmp_path / "wide-cells"
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
            str(wide_regional.HEADER.parent),
            str(source),
            "-o",
            str(test),
            "-lm",
        ],
        check=True,
        env={**os.environ, "TMPDIR": str(tmp_path)},
    )
    subprocess.run([test], check=True)


def test_width_only_region_and_boundaries_and_public_abi():
    source = ordinary_front_build.SOURCE
    native = (source / "native_glrt.c").read_text()
    modified = wide_regional.native_glrt(native)
    marker = "    int wide=short_window&&context->rate==10000000u;"
    assert marker in modified
    assert (
        native[native.index("int leo_native_glrt_analyze_short_window(") :]
        == modified[modified.index("int leo_native_glrt_analyze_short_window(") :]
    )
    search = (source / "kernel/private/full_search.c").read_text()
    widened = wide_regional.full_search(search)
    assert widened.count("regional_cfo_limit(w)") == 6
    assert "regional_cfo_bins(w)*(size_t)regional_count" in widened
    assert "frequencies[64],scores[64]" in widened
    assert "scores[2048]" in widened
    presence = (source / "kernel/private/native_presence/presence.c").read_text()
    presence = wide_regional.presence(presence)
    assert "fabs(cfo)>regional_cfo_limit(w)" in presence
    assert "#define WIDE_REGIONAL_BINS 21" in presence and "#define CFO_COUNT 24" in presence
