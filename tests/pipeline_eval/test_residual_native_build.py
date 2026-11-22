from pathlib import Path
import subprocess

from tools.pipeline_eval.variants.experimental.receiver_residual_build import TWO_CARRIER_SOURCE, optional_residual


def test_native_residual_only_factor_stays_rank_one_and_has_no_raw_counterpart(tmp_path):
    source = tmp_path / "two_carrier_receiver.c"
    source.write_text(optional_residual(TWO_CARRIER_SOURCE.read_text()))
    target = tmp_path / "test-residual"
    subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-I",
                    str(TWO_CARRIER_SOURCE.parent), str(source),
                    str(Path(__file__).with_name("test_residual_native.c")), "-lm", "-o", str(target)],
                   check=True, timeout=15)
    subprocess.run([str(target)], check=True, timeout=10)
