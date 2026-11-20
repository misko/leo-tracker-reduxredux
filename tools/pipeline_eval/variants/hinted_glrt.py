"""One-shot external epoch hints for the authenticated four-center wide detector."""

import ctypes as ct
from contextvars import ContextVar
from pathlib import Path

from .wide_regional import replace

HEADER = Path(__file__).with_suffix(".h")
FRAME = 13_333
ENTRY = "leo_native_glrt_analyze_hinted_v1"


def graft(source):
    source = replace(
        source,
        '#include "short_window_glrt.h"',
        '#include "short_window_glrt.h"\n#include "hinted_glrt.h"',
    )
    source = replace(
        source,
        "leo_native_glrt_result *result,leo_native_glrt_profile *profile,int short_window)",
        "leo_native_glrt_result *result,leo_native_glrt_profile *profile,int short_window,\n"
        "    const int32_t hints[2],leo_hinted_glrt_trace *hint_trace)",
    )
    source = replace(
        source,
        "    if(fegetround()!=FE_TONEAREST)return LEO_NATIVE_GLRT_INVALID;",
        """    if(hints && (!short_window || context->rate != 10000000u ||
        context->receiver_count != 2 || context->refinement_mode != 3 ||
        !hint_trace || !leo_hint_valid(hints[0], (int)context->frame) ||
        !leo_hint_valid(hints[1], (int)context->frame)))return LEO_NATIVE_GLRT_INVALID;
    if(fegetround()!=FE_TONEAREST)return LEO_NATIVE_GLRT_INVALID;""",
    )
    source = replace(
        source,
        "        if(count>4)count=4;\n        memset(selected,0,context->frame);",
        """        if(count>4)count=4;
        if(hints)leo_hint_centers(current,count,hints[rx],(int)context->frame,&hint_trace->lanes[rx]);
        memset(selected,0,context->frame);""",
    )
    source = replace(
        source,
        "        size_t offset=(size_t)start_ms*context->rate/1000u;",
        """        if(hints)hint_trace->lanes[rx].active_epochs=context->search->regional_count;
        size_t offset=(size_t)start_ms*context->rate/1000u;""",
    )
    source = replace(
        source, "stride_ms,result,profile,0);", "stride_ms,result,profile,0,NULL,NULL);"
    )
    source = replace(
        source,
        "stride_ms,\n        result,profile,0);",
        "stride_ms,\n        result,profile,0,NULL,NULL);",
    )
    source = replace(
        source,
        "complex_times,20,20,result,profile,1);",
        "complex_times,20,20,result,profile,1,NULL,NULL);",
        count=2,
    )
    return replace(
        source,
        "int leo_native_glrt_analyze_short_window(leo_native_glrt *context,",
        """int leo_native_glrt_analyze_hinted_v1(leo_native_glrt *context,
    const int16_t *ci16,size_t complex_times,const int32_t hints[2],
    leo_native_glrt_result *result,leo_hinted_glrt_trace *trace)
{
    if(!hints || !trace)return LEO_NATIVE_GLRT_INVALID;
    return analyze_profiled(context,ci16,complex_times,20,20,result,NULL,1,hints,trace);
}

int leo_native_glrt_analyze_short_window(leo_native_glrt *context,""",
    )


class Lane(ct.Structure):
    _fields_ = [
        ("count", ct.c_int32),
        ("ordinary", ct.c_int32 * 4),
        ("selected", ct.c_int32 * 4),
        ("active_epochs", ct.c_int32),
    ]


class Trace(ct.Structure):
    _fields_ = [("lanes", Lane * 2)]


def hints_array(hints):
    if len(hints) != 2 or any(
        value is not None and (type(value) is not int or not 0 <= value < FRAME) for value in hints
    ):
        raise ValueError("need one absent or in-frame integer hint per receiver")
    return (ct.c_int32 * 2)(*(-1 if value is None else value for value in hints))


class HintedCall:
    """Use the original Python payload decoder and one-call C arguments on a dedicated context."""

    def __init__(self, context):
        from leo.analysis.starlink.native_short_window import _Result

        if not (
            context.receiver_count == 2
            and context.sample_rate_hz == 10_000_000
            and context.fractional_epoch
        ):
            raise ValueError("hint ABI requires dual-RX 10 MS/s fractional short windows")
        self.context = context
        self.arguments = ContextVar("hinted_glrt_arguments", default=None)
        entry = getattr(context._library, ENTRY)
        entry.argtypes = [
            ct.c_void_p,
            ct.POINTER(ct.c_int16),
            ct.c_size_t,
            ct.POINTER(ct.c_int32),
            ct.POINTER(_Result),
            ct.POINTER(Trace),
        ]
        entry.restype = ct.c_int
        ordinary = context._analyze

        def dispatch(native, raw, count, output):
            supplied = self.arguments.get()
            if supplied is None:
                return ordinary(native, raw, count, output)
            hints, trace = supplied
            return entry(native, raw, count, hints, output, ct.byref(trace))

        context._analyze = dispatch

    def __call__(self, samples, hints=(None, None), *, timings=False):
        trace = Trace()
        token = self.arguments.set((hints_array(hints), trace))
        try:
            result = self.context.analyze(samples, include_timings=timings)
        finally:
            self.arguments.reset(token)
        lanes = [
            dict(
                ordinary=list(lane.ordinary[: lane.count]),
                selected=list(lane.selected[: lane.count]),
                active_epochs=lane.active_epochs,
            )
            for lane in trace.lanes
        ]
        return result, lanes
