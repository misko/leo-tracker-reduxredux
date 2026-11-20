import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tools.pipeline_eval.qualification import differential_pilot_eval, folded_cfo_eval
from tools.pipeline_eval.variants import differential_pilot, folded_cfo


@pytest.mark.parametrize("edge", ("lower", "upper"))
def test_signed_phase_cue_preserves_all_differential_ranks_and_scores(edge):
    iq, target = differential_pilot_eval.synthetic(edge, "strong")
    inquiry = folded_cfo.score_and_phase(iq, edge)
    assert [(ranks, scores) for ranks, scores, _ in inquiry] == differential_pilot.scout(iq, edge)
    period = folded_cfo.PERIOD
    for ranks, _, phase in inquiry:
        assert ranks[0] == target["epoch"]
        distance = abs((phase - target["cfo_hz"] + period / 2) % period - period / 2)
        assert distance < 1000


def test_unobservable_phase_supplies_no_hint():
    iq = np.zeros((differential_pilot.SAMPLES, 2, 2), dtype="<i2")
    assert folded_cfo.score_and_phase(iq, "lower") == [([], [], None)] * 2


def test_new_holdout_ignores_early_and_duplicate_visits():
    rows = []
    for visit, kind, strata in (
        (1, "miss", "weak"),
        (3, "miss", "weak"),
        (3, "miss", "middle"),
        (4, "miss", "middle"),
        (5, "matched", "strong"),
        (6, "miss", "strong"),
    ):
        rows.append(dict(visit=visit, kind=kind, stratum=strata))
    picked = folded_cfo_eval.choose(2, rows)
    assert [r["visit"] for r in picked] == [3, 4, 5, 6]


def test_compiled_mask_keeps_every_alias_and_exact_tap_arithmetic(tmp_path):
    cc = shutil.which("cc")
    assert cc, "native component tests require a C compiler"
    source = Path(__file__).with_name("test_folded_cfo_mask.c")
    output = tmp_path / "test-folded-cfo"
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
            str(folded_cfo.HEADER.parent),
            str(source),
            "-o",
            str(output),
            "-lm",
        ],
        check=True,
    )
    subprocess.run([output], check=True)
