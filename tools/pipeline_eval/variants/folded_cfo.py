"""Use the complex differential-pilot correlation to mask only new hint CFO cells."""

import ctypes as ct
from contextvars import ContextVar
from pathlib import Path

import numpy as np

from . import differential_pilot as dp
from .hinted_glrt import Trace, hints_array
from .wide_regional import replace

ENTRY = "leo_native_glrt_analyze_phase_hint_v1"
HEADER = Path(__file__).with_name("folded_cfo_mask.h")
PERIOD = dp.RATE / dp.LAG


def score_and_phase(samples, edge):
    """Preserve the frozen score ordering and retain folded phase at both leading starts."""
    if samples.shape != (dp.SAMPLES, 2, 2) or samples.dtype != np.dtype("<i2"):
        raise ValueError("Phase hint requires exact 20 ms dual CI16 at 10 MS/s")
    x = np.empty((2, dp.SAMPLES), dtype=np.complex64)
    x.real, x.imag = samples[:, :, 0].T, samples[:, :, 1].T
    pairs = x[:, : -dp.LAG].conj()
    pairs *= x[:, dp.LAG :]
    pairs -= pairs.mean(axis=-1, dtype=np.complex128, keepdims=True)
    folded = np.fft.fft(dp.fold_products(pairs), n=dp.FFT, axis=-1)
    correlations, scores = [], []
    for kernel, energy in dp.filters(edge):
        result = np.fft.ifft(np.einsum("lrf,rf->lf", folded, kernel), axis=-1)[:, : dp.FRAME]
        correlations.append(result)
        scores.append(abs(result) ** 2 / energy)
    values = scores[0] - scores[1]
    out = []
    for lane, row in enumerate(values):
        ranks = dp.ranked_centers(row)
        z = complex(correlations[0][lane, ranks[0]]) if ranks else 0j
        hz = np.angle(z) * (PERIOD / (2 * np.pi)) if z else None
        out.append((ranks, [float(row[e]) for e in ranks], hz))
    return out


def presence(source):
    return replace(
        source,
        "    int regional_count, wide_regional;",
        """    int regional_count, wide_regional;
    int folded_epoch, folded_tracking;
    unsigned folded_masks[3];
    uint64_t folded_anchor_bins, folded_complex_taps;""",
    )


def coarse(source):
    header = '#include "wide_regional_cfo.h"'
    source = replace(source, header, header + '\n#include "folded_cfo_mask.h"')
    marker = (
        "        if (w->wide_regional) wide_regional_float_add(samples,real,imag,taps,inverse,sum);"
    )
    source = replace(
        source,
        marker,
        """        unsigned mask=w->folded_tracking ? folded_epoch_mask(w,epoch) : 0;
        if (w->folded_tracking) {
            unsigned bins=mask ? folded_cfo_count(mask) : (unsigned)regional_cfo_bins(w);
            w->folded_anchor_bins+=bins;
            w->folded_complex_taps+=(uint64_t)taps*bins;
        }
        if (mask) folded_cfo_float_add(samples,real,imag,taps,inverse,sum,mask);
        else if (w->wide_regional) wide_regional_float_add(samples,real,imag,taps,inverse,sum);""",
    )
    marker = "    return 0;\n}\n\n#pragma GCC pop_options"
    return replace(
        source,
        marker,
        """    if (w->folded_tracking) for (int i=0; i<3; ++i) {
        unsigned mask=w->folded_masks[i];
        int epoch=w->folded_epoch-1+i;
        if (!mask || epoch<0 || epoch>=(int)w->n) continue;
        for (int f=0; f<WIDE_REGIONAL_BINS; ++f) if (!(mask&(1u<<f)))
            w->grid[f*w->n+epoch]=-INFINITY;
    }
"""
        + marker,
    )


def native(source):
    source = replace(
        source,
        '#include "hinted_glrt.h"',
        """#include "hinted_glrt.h"

typedef struct {
    uint64_t grid_cells, anchor_bins, complex_taps;
} leo_folded_lane;""",
    )
    source = replace(
        source,
        "const int32_t hints[2],leo_hinted_glrt_trace *hint_trace)",
        "const int32_t hints[2],leo_hinted_glrt_trace *hint_trace,\n"
        "    const double folded[2],leo_folded_lane folded_trace[2])",
    )
    source = replace(
        source,
        "        size_t offset=(size_t)start_ms*context->rate/1000u;",
        """        leo_presence_workspace *search_workspace=context->search;
        search_workspace->folded_tracking=folded_trace!=NULL;
        if (folded_trace) {
            search_workspace->folded_epoch=-10;
            search_workspace->folded_anchor_bins=search_workspace->folded_complex_taps=0;
            memset(search_workspace->folded_masks,0,sizeof(search_workspace->folded_masks));
            folded_trace[rx].grid_cells=(uint64_t)regional_cfo_bins(search_workspace)
                *search_workspace->regional_count;
            if (fabs(folded[rx])<=10000000.0/88.0 && wide && count==4
                && current[3]!=hint_trace->lanes[rx].ordinary[3]) {
                unsigned mask=folded_cfo_mask(search_workspace,folded[rx]);
                search_workspace->folded_epoch=current[3];
                for (int i=0; mask && i<3; ++i) {
                    int e=current[3]+i-1;
                    if (e<0 || e>=(int)context->frame) continue;
                    if (abs(e-current[0])<=2 || abs(e-current[1])<=2 ||
                        abs(e-current[2])<=2) continue;
                    search_workspace->folded_masks[i]=mask;
                    folded_trace[rx].grid_cells-=WIDE_REGIONAL_BINS-folded_cfo_count(mask);
                }
            }
        }
        size_t offset=(size_t)start_ms*context->rate/1000u;""",
    )
    source = replace(
        source,
        "        copy_row(&temporary.rows[temporary.row_count++],rx,(int)window,",
        """        if (folded_trace) {
            folded_trace[rx].anchor_bins=search_workspace->folded_anchor_bins;
            folded_trace[rx].complex_taps=search_workspace->folded_complex_taps;
        }
        search_workspace->folded_tracking=0;
        copy_row(&temporary.rows[temporary.row_count++],rx,(int)window,""",
    )
    # Preserve all original public wrappers and the preexisting hinted entry.
    source = replace(source, ",NULL,NULL);", ",NULL,NULL,NULL,NULL);", count=4)
    source = replace(
        source,
        "20,20,result,NULL,1,hints,trace);",
        "20,20,result,NULL,1,hints,trace,NULL,NULL);",
    )
    marker = "int leo_native_glrt_analyze_hinted_v1(leo_native_glrt *context,"
    return replace(
        source,
        marker,
        f"""int {ENTRY}(leo_native_glrt *context,
    const int16_t *ci16,size_t complex_times,const int32_t hints[2],const double folded[2],
    leo_native_glrt_result *result,leo_hinted_glrt_trace *trace,leo_folded_lane folded_trace[2])
{{
    if(!hints || !folded || !trace || !folded_trace)return LEO_NATIVE_GLRT_INVALID;
    return analyze_profiled(context,ci16,complex_times,20,20,result,NULL,1,
        hints,trace,folded,folded_trace);
}}

"""
        + marker,
    )


class Lane(ct.Structure):
    _fields_ = [(f, ct.c_uint64) for f in ("grid_cells", "anchor_bins", "complex_taps")]


class BandCall:
    def __init__(self, context):
        from leo.analysis.starlink.native_short_window import _Result

        self.context = context
        self.arguments = ContextVar("folded_cfo_arguments", default=None)
        entry = getattr(context._library, ENTRY)
        entry.argtypes = [
            ct.c_void_p,
            ct.POINTER(ct.c_int16),
            ct.c_size_t,
            ct.POINTER(ct.c_int32),
            ct.POINTER(ct.c_double),
            ct.POINTER(_Result),
            ct.POINTER(Trace),
            ct.POINTER(Lane),
        ]
        entry.restype = ct.c_int
        original = context._analyze

        def dispatch(native, raw, count, output):
            args = self.arguments.get()
            if args is None:
                return original(native, raw, count, output)
            hints, folded, trace, lanes = args
            return entry(native, raw, count, hints, folded, output, ct.byref(trace), lanes)

        context._analyze = dispatch

    def __call__(self, samples, hints, frequencies):
        trace, lanes = Trace(), (Lane * 2)()
        folded = (ct.c_double * 2)(*(1e9 if f is None else f for f in frequencies))
        token = self.arguments.set((hints_array(hints), folded, trace, lanes))
        try:
            outcome = self.context.analyze(samples, include_timings=True)
        finally:
            self.arguments.reset(token)
        taps = [dict((k, getattr(r, k)) for k, _ in Lane._fields_) for r in lanes]
        return outcome, taps
