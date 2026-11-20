"""Add independent timing support without dropping the stock wide regions."""

import ctypes as ct
from pathlib import Path

from . import hinted_glrt
from .differential_runtime import DifferentialCall
from .wide_regional import replace

HEADER = Path(__file__).with_suffix(".h")
ENTRY = "leo_native_glrt_analyze_center_union_v1"


def native(source):
    source = hinted_glrt.graft(source)
    source = replace(source, '"hinted_glrt.h"', '"center_union.h"')
    source = source.replace("leo_hinted_glrt_trace", "leo_center_union_trace")
    source = replace(source, hinted_glrt.ENTRY, ENTRY)
    source = replace(
        source,
        "        if(hints)leo_hint_centers(current,count,hints[rx],(int)context->frame,"
        "&hint_trace->lanes[rx]);\n",
        """        leo_center_union_lane *lane=hints ? &hint_trace->lanes[rx] : NULL;
        if(lane){
            *lane=(leo_center_union_lane){.count=count,.hint=hints[rx]};
            memcpy(lane->ordinary,current,(size_t)count*sizeof(*current));
        }
""",
    )
    source = replace(
        source,
        "        context->search->regional_count=0;",
        """        if(lane)lane->added_epochs=leo_union_add(selected,(int)context->frame,hints[rx]);
        context->search->regional_count=0;""",
    )
    source = replace(
        source,
        """        for(size_t epoch=0;epoch<context->frame;++epoch)
            if(selected[epoch])context->search->regional_epochs[
                context->search->regional_count++]=(int)epoch;
        if(hints)hint_trace->lanes[rx].active_epochs=context->search->regional_count;""",
        """        for(size_t epoch=0;epoch<context->frame;++epoch)if(selected[epoch]){
            context->search->regional_epochs[context->search->regional_count++]=(int)epoch;
            if(lane && selected[epoch]==1)lane->stock_epochs[lane->stock_epoch_count++]=(int)epoch;
        }
        if(lane)lane->active_epochs=context->search->regional_count;
        context->search->center_union_lane=lane;
        context->search->center_union_mask=lane ? selected : NULL;""",
    )
    source = replace(
        source,
        "        if(leo_full_search_run_prepared_with_fine_workspace_mode(context->search,",
        "        int search_failed=leo_full_search_run_prepared_with_fine_workspace_mode("
        "context->search,",
    )
    return replace(
        source,
        "            context->search->regional_count)){",
        """            context->search->regional_count);
        context->search->center_union_lane=NULL;
        context->search->center_union_mask=NULL;
        if(search_failed){""",
    )


def presence(source):
    return replace(
        source,
        "    int regional_epochs[13334];",
        """    int regional_epochs[13334];
    leo_center_union_lane *center_union_lane;
    const unsigned char *center_union_mask;""",
    )


def full_search(source):
    source = replace(
        source,
        "    size_t count=0;\n    for(int f=0;f<regional_cfo_bins(w);++f)"
        "for(int i=0;i<epoch_count;",
        """    size_t count=0;
    if(w->center_union_lane){
        leo_center_union_lane *lane=w->center_union_lane;
        const unsigned char *mask=w->center_union_mask;
        for(int f=0;f<regional_cfo_bins(w);++f){
            const double *row=w->grid+f*w->n;
            int stock_slot=0;
            for(int i=0;i<epoch_count;++i){
                const int epoch=epochs[i], stock=mask[epoch]==1;
                if(leo_union_local_peak(row,mask,(int)w->n,epoch)){
                    peaks[count++]=(leo_full_search_peak){row[epoch],epoch,f};
                    if(stock){
                        lane->stock_peak_masks[stock_slot]|=UINT32_C(1)<<f;
                        ++lane->stock_peaks;
                    }else ++lane->extra_peaks;
                }
                stock_slot+=stock;
            }
        }
        return count;
    }
    for(int f=0;f<regional_cfo_bins(w);++f)for(int i=0;i<epoch_count;""",
    )
    source = replace(
        source,
        "    free(peaks);\n    /* A nonempty peak inventory",
        """    free(peaks);
    if(w->center_union_lane)for(size_t j=0;j<nr;++j){
        if(w->center_union_mask[retained[j].epoch]==1)++w->center_union_lane->retained_stock;
        else ++w->center_union_lane->retained_extra;
    }
    /* A nonempty peak inventory""",
    )
    return replace(
        source,
        "            if (local>=0 && local<(int)w->n &&\n                (w->grid[f*w->n+local]",
        """            if (local>=0 && local<(int)w->n &&
                (!w->center_union_mask || w->center_union_mask[e]!=1 ||
                    w->center_union_mask[local]==1) &&
                (w->grid[f*w->n+local]""",
    )


class Lane(ct.Structure):
    _fields_ = [
        ("count", ct.c_int32),
        ("ordinary", ct.c_int32 * 4),
        ("hint", ct.c_int32),
        ("added_epochs", ct.c_int32),
        ("active_epochs", ct.c_int32),
        ("stock_epoch_count", ct.c_int32),
        ("stock_epochs", ct.c_int32 * 12),
        ("stock_peak_masks", ct.c_uint32 * 12),
        ("stock_peaks", ct.c_int32),
        ("extra_peaks", ct.c_int32),
        ("retained_stock", ct.c_int32),
        ("retained_extra", ct.c_int32),
    ]


class Trace(ct.Structure):
    _fields_ = [("lanes", Lane * 2)]


class UnionCall:
    def __init__(self, context):
        from contextvars import ContextVar

        from leo.analysis.starlink.native_short_window import _Result

        if not (
            context.receiver_count == 2
            and context.sample_rate_hz == 10_000_000
            and context.fractional_epoch
        ):
            raise ValueError("center-union ABI requires the fixed dual-RX fractional geometry")
        self.context = context
        self.arguments = ContextVar("union_arguments", default=None)
        shim = getattr(context._library, ENTRY)
        shim.argtypes = [
            ct.c_void_p,
            ct.POINTER(ct.c_int16),
            ct.c_size_t,
            ct.POINTER(ct.c_int32),
            ct.POINTER(_Result),
            ct.POINTER(Trace),
        ]
        shim.restype = ct.c_int
        ordinary = context._analyze

        def dispatch(native, raw, count, output):
            args = self.arguments.get()
            if args is None:
                return ordinary(native, raw, count, output)
            hints, trace = args
            return shim(native, raw, count, hints, output, ct.byref(trace))

        context._analyze = dispatch

    def __call__(self, samples, hints=(None, None), *, timings=False):
        trace = Trace()
        token = self.arguments.set((hinted_glrt.hints_array(hints), trace))
        try:
            payload = self.context.analyze(samples, include_timings=timings)
        finally:
            self.arguments.reset(token)
        output = []
        for lane in trace.lanes:
            original = list(lane.ordinary[: lane.count])
            output.append(
                dict(
                    ordinary=original,
                    selected=original + ([lane.hint] if lane.added_epochs else []),
                    active_epochs=lane.active_epochs,
                    added_epochs=lane.added_epochs,
                    stock_peak_keys=[
                        (epoch, f)
                        for epoch, bits in zip(
                            lane.stock_epochs[: lane.stock_epoch_count],
                            lane.stock_peak_masks[: lane.stock_epoch_count],
                            strict=True,
                        )
                        for f in range(21)
                        if bits & (1 << f)
                    ],
                    stock_peaks=lane.stock_peaks,
                    extra_peaks=lane.extra_peaks,
                    retained_stock=lane.retained_stock,
                    retained_extra=lane.retained_extra,
                )
            )
        return payload, output


class DifferentialUnionCall(DifferentialCall):
    def __init__(self, native, edge, *, scout):
        self.native = native
        self.edge = edge
        self.scout = scout
        self.hinted = UnionCall(native)
