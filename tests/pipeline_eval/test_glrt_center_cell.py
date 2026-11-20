import subprocess

import pytest

from tools.pipeline_eval.qualification import glrt_center_cell_eval as run
from tools.pipeline_eval.variants import glrt_center_cell as variant

CORE = """
#include <assert.h>
#include <stdlib.h>

static int calls;
struct workspace { int acquisition_first_frame; };
struct scores { double acquired_cfo_hz, exact_score, control_score; };
struct final { struct scores candidate; int glrt_complete; };

static int glrt(struct workspace *w, int count, int epoch, double cfo, double offset,
    int frames, int final_scoring, double score[3])
{
    ++calls;
    score[0]=epoch+0.125;
    score[1]=epoch+0.25;
    return 0;
}

static int visit(int frame, int complete, int expected)
{
    struct workspace value = {frame}, *w = &value;
    struct final current = {{500.0, 2.125, 2.25}, complete}, *candidate = &current;
    int count = 100, epoch;
    calls=0;
    for(int k=0;k<5;++k){
        epoch=k;
        double score[3];
"""
END = """
        assert(score[0]==k+0.125 && score[1]==k+0.25);
    }
    return calls!=expected;
}

int main(void) {
    return visit(0,1,EXPECTED) || visit(0,0,5) || visit(1,1,5);
}
"""


@pytest.mark.parametrize(
    ("frames", "diverse", "energy", "calls"),
    [(16, 0, 0, 4), (8, 0, 0, 5), (16, 1, 0, 5), (16, 0, 1, 5)],
)
def test_compiled_lattice_only_reuses_completed_equivalent_score(
    tmp_path, frames, diverse, energy, calls
):
    source, exe = tmp_path / "test.c", tmp_path / "test"
    source.write_text(variant.overlay(CORE + variant._ORIGINAL + END))
    subprocess.run(
        [
            "cc",
            "-std=c11",
            f"-DLEO_PRESENCE_EPOCH_FRAMES={frames}",
            f"-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY={diverse}",
            f"-DLEO_PRESENCE_ENERGY_SYMBOL_SUPPORT={energy}",
            f"-DEXPECTED={calls}",
            str(source),
            "-o",
            str(exe),
        ],
        check=True,
    )
    subprocess.run([str(exe)], check=True)


def test_held_ranking_ignores_results_and_is_order_independent():
    rows = [
        dict(visit=i, segment=3, sequence=i, iq_sha256=str(i), status="processed") for i in range(6)
    ]
    rows[1]["status"] = "invalid_capture"
    expected = {r["visit"]: r["cohort"] for r in run.roster("DS29-0082", rows)}
    for row in rows:
        row["qualification_result"] = 20 - row["visit"]
    seen = run.roster("DS29-0082", rows[::-1])
    assert {r["visit"]: r["cohort"] for r in seen} == expected
    assert expected[1] == "excluded"
    assert list(expected.values()).count("held") == 2


def test_overlay_rejects_an_unrecognized_scoring_call():
    with pytest.raises(ValueError, match="five-cell GLRT source binding"):
        variant.overlay(variant._ORIGINAL + variant._ORIGINAL)
