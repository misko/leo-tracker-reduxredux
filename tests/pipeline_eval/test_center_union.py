import os
import subprocess
from pathlib import Path

import pytest

from tools.pipeline_eval import wide_runtime
from tools.pipeline_eval.qualification import center_union_gate
from tools.pipeline_eval.variants import center_union


def test_native_union_clips_deduplicates_and_preserves_stock_local_peaks(tmp_path):
    wide_runtime.unpack(wide_runtime.CAPSULE, tmp_path / "capsule")
    executable = tmp_path / "probe"
    subprocess.run(
        [
            "cc",
            "-O2",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(tmp_path / "capsule/source"),
            "-I",
            str(center_union.HEADER.parent),
            str(Path(__file__).with_name("center_union_probe.c")),
            "-o",
            str(executable),
        ],
        check=True,
        env={**os.environ, "TMPDIR": str(tmp_path)},
    )
    subprocess.run([str(executable)], check=True)


def test_gate_checks_actual_nomination_keys_and_not_only_counts():
    control = dict(ordinary=[3], stock_peak_keys=[(2, 0), (3, 2)], stock_peaks=2, active_epochs=3)
    accepted = dict(control, active_epochs=5, added_epochs=2)
    center_union_gate.preserved([control], [accepted])
    changed = dict(accepted, stock_peak_keys=[(2, 0), (3, 3)])
    with pytest.raises(ValueError, match="lost an original native peak"):
        center_union_gate.preserved([control], [changed])
