import shutil
import subprocess
from pathlib import Path

from tools.pipeline_eval.qualification import ordinary_glrt_build


def test_retained_band_and_ci16_power(tmp_path):
    cc = shutil.which("cc")
    assert cc, "native component tests require a C compiler"
    target = tmp_path / "ordinary_glrt_fine"
    source = Path(__file__).with_name("ordinary_glrt_fine.c")
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ordinary_glrt_build.HEADER.parent),
            str(source),
            "-o",
            str(target),
            "-lm",
        ],
        check=True,
    )
    subprocess.run([target], check=True)


def test_wave8_replay_only_changes_fine_acquisition_cache():
    source = ordinary_glrt_build.stock.SOURCE / "kernel/private/fine_precision.h"
    stock = source.read_text()
    candidate = ordinary_glrt_build.overlay(stock)
    fft = "fftwf_execute(workspace->plan);"
    guard = "#if LEO_FINE_PRECISION_GUARDED\n    ++cache->guard_checks;"
    assert stock.count(fft) == candidate.count(fft) == 1
    assert stock[stock.index(guard) :] == candidate[candidate.index(guard) :]
    assert "leo_fine_span_energy(w->prefix,start+begin,start+end)" in candidate
