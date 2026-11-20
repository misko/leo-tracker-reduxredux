import subprocess

import pytest

from tools.pipeline_eval.qualification.paired_epoch_eval import members
from tools.pipeline_eval.variants import paired_epoch_overlay as overlay


def test_native_union_preserves_membership_order_edges_and_overlap(tmp_path):
    source, program = tmp_path / "union.c", tmp_path / "test-union"
    source.write_text(
        """
#include <stdint.h>
#include "paired_epoch_union.h"

int main(void)
{
    unsigned char selected[16]={0};
    int left[4]={0,7,8,7},right[4]={2,7,15,15};
    const int expected[16]={1,1,1,1,0,0,1,1,1,1,0,0,0,0,1,1};
    paired_epoch_mark(selected,16,left,4);
    paired_epoch_mark(selected,16,right,4);
    for(int k=0;k<16;++k)if(selected[k]!=expected[k])return 1;
    return 0;
}
"""
    )
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(overlay.HEADER.parent),
            str(source),
            "-o",
            str(program),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(program)], check=True)
    assert members([0, 7, 8, 7, 2, 7, 15, 15], 16) == [0, 1, 2, 3, 6, 7, 8, 9, 14, 15]
    assert members([], 16) == []


def test_overlay_rejects_unpinned_or_duplicate_edit_locations():
    with pytest.raises(ValueError, match="unrecognized"):
        overlay.overlay('#include "short_window_glrt.h"')
    with pytest.raises(ValueError, match="unrecognized"):
        overlay.replace("x x", "x", "y")
    assert overlay.replace("x z", "x", "y") == "y z"
