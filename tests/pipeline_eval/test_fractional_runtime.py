import subprocess
from pathlib import Path

import pytest

from tools.pipeline_eval.qualification import ordinary_front_build
from tools.pipeline_eval.variants import fractional_runtime_overlay as variant


@pytest.mark.parametrize("flags", [(), ("-U__SSE2__",)], ids=["native-packed", "scalar"])
def test_ordered_16_taps_are_exact_across_rounding_boundaries(tmp_path, flags):
    executable = tmp_path / "check_fraction"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O3",
            "-fno-fast-math",
            "-ffp-contract=off",
            "-fcx-limited-range",
            *flags,
            "-I",
            str(variant.HEADER.parent),
            str(Path(__file__).with_name("fractional_runtime_probe.c")),
            "-o",
            str(executable),
            "-lm",
        ],
        check=True,
    )
    subprocess.run([str(executable)], check=True)


def test_overlay_rejects_changed_native_reuse_points():
    source = (ordinary_front_build.SOURCE / "kernel/private/native_presence/presence.c").read_text()
    assert '#include "fractional_runtime.h"' in variant.overlay(source)
    with pytest.raises(ValueError, match="source binding"):
        variant.overlay(source.replace(variant.CACHE, ""))
