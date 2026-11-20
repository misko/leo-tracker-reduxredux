import subprocess
from pathlib import Path

from tools.pipeline_eval.qualification import ordinary_front_build


def test_fractional_dot_matches_scalar_across_binades_and_tails(tmp_path):
    fixture = Path(__file__).with_name("ordinary_front_filter.c")
    executable = tmp_path / "ordinary-front-filter"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O3",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fno-fast-math",
            "-fcx-limited-range",
            "-I",
            str(ordinary_front_build.HEADER.parent),
            str(fixture),
            "-lm",
            "-o",
            str(executable),
        ],
        check=True,
    )
    subprocess.run([str(executable)], check=True)


def test_overlay_changes_only_the_continuous_sample_path():
    source = ordinary_front_build.SOURCE / "kernel/private/native_presence/presence.c"
    original = source.read_text()
    edited = ordinary_front_build.overlay(original)
    prefix = "static double sinc"
    assert original[: original.index(prefix)] == edited[: edited.index(prefix)]
    footer = "                /* Omit only the common unit-magnitude frame phase. */"
    assert original[original.index(footer) :] == edited[edited.index(footer) :]
