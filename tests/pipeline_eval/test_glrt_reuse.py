import os
import platform
import subprocess
from pathlib import Path

import pytest

from tools.pipeline_eval import wide_runtime
from tools.pipeline_eval.variants import glrt_reuse


@pytest.mark.hardware
@pytest.mark.skipif(platform.machine() != "x86_64", reason="x86 packed receiver preparation")
def test_dual_prepare_rounding_and_unsigned_energy_at_fixed_max_count(tmp_path):
    wide_runtime.unpack(wide_runtime.CAPSULE, tmp_path / "capsule")
    exe = tmp_path / "probe"
    subprocess.run(
        [
            "cc",
            "-O3",
            "-std=c11",
            "-fno-fast-math",
            "-ffp-contract=off",
            "-fcx-limited-range",
            "-I",
            str(tmp_path / "capsule/source"),
            "-I",
            str(glrt_reuse.HEADER.parent),
            str(Path(__file__).with_name("glrt_reuse_prepare_probe.c")),
            "-o",
            str(exe),
        ],
        check=True,
        env={**os.environ, "TMPDIR": str(tmp_path)},
    )
    completed = subprocess.run([str(exe)], check=False)
    if completed.returncode == 77:
        pytest.skip("the AVX2 preparation branch requires AVX2")
    assert completed.returncode == 0


def test_prepare_overlay_fails_closed_when_the_stock_include_changes():
    with pytest.raises(ValueError, match="exact archived source anchor"):
        glrt_reuse.overlay('#include "input.h"')
