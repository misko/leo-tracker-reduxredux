import platform
import subprocess
from pathlib import Path

import pytest

from tools.pipeline_eval.variants import wide_kernel


@pytest.mark.hardware
@pytest.mark.skipif(platform.machine() != "x86_64", reason="x86 packed interpolation probe")
def test_fractional_batch_preserves_binary64_sums_and_scalar_remainder(tmp_path):
    exe = tmp_path / "probe"
    subprocess.run(
        [
            "cc",
            "-O3",
            "-std=c11",
            "-fno-fast-math",
            "-ffp-contract=off",
            "-fcx-limited-range",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(wide_kernel.HEADER.parent),
            str(Path(__file__).with_name("wide_kernel_probe.c")),
            "-lm",
            "-o",
            str(exe),
        ],
        check=True,
    )
    result = subprocess.run([str(exe)], check=False)
    if result.returncode == 77:
        pytest.skip("the ordered packed convolution probe requires AVX2")
    assert result.returncode == 0


def test_overlay_refuses_to_patch_an_unrecognized_or_ambiguous_native_source():
    with pytest.raises(ValueError, match="unique source anchor"):
        wide_kernel.overlay('#include "fractional_runtime.h"\n' * 2)
