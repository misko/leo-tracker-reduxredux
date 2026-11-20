"""Route a physical lane of interleaved CI16 into the existing one-RX pipeline."""

from .wide_regional import replace

SYMBOL = "leo_one_lane_strided_short_v1"


def dwell(source):
    start = source.index("static int leo_dwell_input_prepare_single_reuse(")
    end = source.index("static int leo_dwell_input_prepare_single(", start)
    helper = source[start:end].replace("prepare_single_reuse(", "prepare_one_strided(")
    helper = replace(
        helper, "ci16[2*k],imag=(double)ci16[2*k+1]", "ci16[4*k],imag=(double)ci16[4*k+1]"
    )
    return source[:end] + helper + source[end:]


def kernel(source):
    source = replace(
        source,
        "const int32_t hints[2],leo_center_union_trace *hint_trace)\n{",
        "const int32_t hints[2],leo_center_union_trace *hint_trace,int physical_lane)\n{",
    )
    source = replace(
        source,
        "    int prepare_failed=context->receiver_count==1\n",
        "    int prepare_failed=physical_lane>=0\n"
        "        ? leo_dwell_input_prepare_one_strided(prepared_view,ci16+2*physical_lane,\n"
        "            prepare_count)\n"
        "        : context->receiver_count==1\n",
    )
    source = replace(
        source,
        "            if((context->receiver_count==1\n",
        "            if((physical_lane>=0\n"
        "                ? leo_proposal_top4(context->proposal,ci16,0,physical_lane,\n"
        "                    centers[anchor][rx],&counts[anchor][rx],&timings[anchor][rx])\n"
        "                : context->receiver_count==1\n",
    )
    source = replace(
        source, "result,profile,0,NULL,NULL);", "result,profile,0,NULL,NULL,-1);", count=2
    )
    source = replace(
        source, "result,profile,1,NULL,NULL);", "result,profile,1,NULL,NULL,-1);", count=2
    )
    source = replace(source, "result,NULL,1,hints,trace);", "result,NULL,1,hints,trace,-1);")
    return (
        source
        + f"""

/* Select one lane before proposal, preparation or search; output remains logical RX0. */
int {SYMBOL}(leo_single_rx_glrt *context, const int16_t *ci16,
    size_t complex_times, int physical_lane, leo_native_glrt_result *result)
{{
    if(!context||context->magic!=LEO_SINGLE_RX_GLRT_CONTEXT_MAGIC||
       !context->native||context->native->magic!=LEO_NATIVE_GLRT_CONTEXT_MAGIC||
       context->native->receiver_count!=1||physical_lane<0||physical_lane>1)
        return LEO_NATIVE_GLRT_INVALID;
    return analyze_profiled(context->native,ci16,complex_times,20,20,result,
        NULL,1,NULL,NULL,physical_lane);
}}
"""
    )
