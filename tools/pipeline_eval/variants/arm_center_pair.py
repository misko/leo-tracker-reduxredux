"""Compose the old center reuse with an exact portable pair of original starts."""

from pathlib import Path

from ..qualification.fractional_cost_build import presence
from . import glrt_center_cell
from .wide_regional import replace

HEADER = Path(__file__).with_suffix(".h")

TRACE_CODE = """#ifdef LEO_ARM_CENTER_TRACE
static uint64_t leo_arm_center_counts[4];
void leo_arm_center_trace(uint64_t result[4])
{
    memcpy(result,leo_arm_center_counts,sizeof(leo_arm_center_counts));
    memset(leo_arm_center_counts,0,sizeof(leo_arm_center_counts));
}
#define LEO_CENTER_COUNT(slot,value) (leo_arm_center_counts[(slot)]+=(value))
#else
#define LEO_CENTER_COUNT(slot,value) ((void)0)
#endif

"""


def paired_presence(source):
    return replace(
        presence(source), '#include "fractional_cost_integer.h"', '#include "arm_center_pair.h"'
    )


def search(source, mode, trace=False):
    if mode not in ("original", "center", "pair"):
        raise ValueError("unsupported fractional search variant")
    if mode != "original":
        source = glrt_center_cell.overlay(source)
    if trace:
        source = replace(
            source,
            "static int full_fractional_epoch(",
            TRACE_CODE + "static int full_fractional_epoch(",
        )
        source = replace(
            source,
            glrt_center_cell._ORIGINAL,
            "        {\n        LEO_CENTER_COUNT(0,1);\n"
            + glrt_center_cell._ORIGINAL
            + "        }\n",
        )
        if mode != "original":
            source = replace(
                source,
                "            score[0]=candidate->candidate.exact_score;",
                "            LEO_CENTER_COUNT(1,1);\n"
                "            score[0]=candidate->candidate.exact_score;",
            )
    if mode == "pair":
        loop = "    for(int k=0;k<5;++k){\n        int epoch="
        source = replace(
            source, loop, "    double paired_scores[2][3];\n    int paired=0;\n" + loop
        )
        instrumentation = (
            "\n            if(paired){LEO_CENTER_COUNT(2,1);LEO_CENTER_COUNT(3,used_frames);}"
            if trace
            else ""
        )
        source = replace(
            source,
            "        double score[3];\n#if LEO_PRESENCE_EPOCH_FRAMES == 16",
            """        double score[3];
        if(k==0||k==3){
            unsigned used_frames;
            paired=leo_center_pair(w,count,epoch,candidate->candidate.acquired_cfo_hz,
                paired_scores,&used_frames);"""
            + instrumentation
            + """
        }
        if(k!=2&&paired){
            const int p=(k==1||k==4);
            score[0]=paired_scores[p][0];
            score[1]=paired_scores[p][1];
        } else
#if LEO_PRESENCE_EPOCH_FRAMES == 16""",
        )
    return source
