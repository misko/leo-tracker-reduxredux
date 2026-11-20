import os
import subprocess

import pytest

from tools.pipeline_eval.qualification.hinted_glrt_trial import sham
from tools.pipeline_eval.variants import hinted_glrt


@pytest.mark.parametrize("hints", [(1,), (True, None), (None, -1), (13333, 0), (0.5, 0)])
def test_epoch_hint_port_rejects_out_of_contract_input(hints):
    with pytest.raises(ValueError, match="in-frame integer"):
        hinted_glrt.hints_array(hints)


def test_absence_and_random_control_are_bound_to_receiver():
    assert list(hinted_glrt.hints_array((None, 0))) == [-1, 0]
    assert list(hinted_glrt.hints_array((13332, None))) == [13332, -1]
    first = sham("DS26-0237", 68, 0)
    assert first == sham("DS26-0237", 68, 0)
    assert 0 <= first < 13333
    assert first != sham("DS26-0237", 68, 1)


def test_native_geometry_uses_at_most_four_centers_and_preserves_the_first_three(tmp_path):
    (tmp_path / "native_glrt.h").write_text(
        "#include <stdint.h>\n#include <stddef.h>\n"
        "typedef struct leo_native_glrt leo_native_glrt;\n"
        "typedef struct leo_native_glrt_result leo_native_glrt_result;\n"
    )
    executable = tmp_path / "hint-test"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(tmp_path),
            "-I",
            str(hinted_glrt.HEADER.parent),
            "-x",
            "c",
            "-",
            "-o",
            str(executable),
        ],
        input="""
#include <assert.h>
#include "hinted_glrt.h"
int main(void) {
    leo_hint_lane lane;
    int centers[] = {0, 430, 5000, 8000};
    leo_hint_centers(centers,4,-1,13333,&lane);
    assert(lane.count==4 && lane.selected[3]==8000);
    leo_hint_centers(centers,4,13332,13333,&lane);
    assert(lane.selected[3]==8000); /* Circular one-sample duplicate. */
    leo_hint_centers(centers,4,5002,13333,&lane);
    assert(lane.selected[3]==8000); /* Intersecting regional neighborhoods. */
    leo_hint_centers(centers,4,701,13333,&lane);
    assert(lane.ordinary[3]==8000 && lane.selected[3]==701);
    assert(centers[0]==0 && centers[1]==430 && centers[2]==5000);
    leo_hint_centers(centers,3,901,13333,&lane);
    assert(lane.count==3 && lane.selected[2]==5000 && lane.selected[3]==0);
    assert(!leo_hint_valid(-2,13333) && !leo_hint_valid(13333,13333));
    return 0;
}
""",
        text=True,
        env=os.environ | {"TMPDIR": str(tmp_path)},
        check=True,
    )
    subprocess.run([executable], check=True)
