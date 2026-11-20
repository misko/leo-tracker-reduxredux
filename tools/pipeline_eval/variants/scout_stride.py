"""Use the even CFO bank and two physical neighboring repairs per scout region."""

from pathlib import Path

from .wide_regional import replace

HEADER = Path(__file__).with_name("scout_stride_coarse.h")


def presence(source):
    source = replace(
        source,
        "    int regional_count, wide_regional;",
        "    int regional_count, wide_regional, scout_stride;",
    )
    return replace(
        source,
        "    double float_reference_energy[12];",
        "    double float_reference_energy[12];\n"
        "    float stride_even_real[12*45*12],stride_even_imag[12*45*12];",
    )


def coarse(source):
    marker = '#include "wide_regional_cfo.h"'
    src = replace(
        source,
        marker,
        marker + '\n\nstatic int coarse_frame_index(int slot);\n#include "scout_stride_coarse.h"',
    )
    marker = (
        "                w->float_reference_imag[index]="
        "(float)(creal(reference)*sine+cimag(reference)*cosine);"
    )
    block = """
                if (!(f&1)) {
                    int packed=symbol*45*12+k*12+f/2;
                    w->stride_even_real[packed]=w->float_reference_real[index];
                    w->stride_even_imag[packed]=w->float_reference_imag[index];
                }"""
    src = replace(src, marker, marker + block)
    marker = (
        "        if (w->wide_regional) wide_regional_float_add(samples,real,imag,taps,inverse,sum);"
    )
    block = """        if (w->scout_stride) scout_stride_even_add(samples,
            w->stride_even_real+symbol*45*12,w->stride_even_imag+symbol*45*12,taps,inverse,sum);
        else if (w->wide_regional) wide_regional_float_add(samples,real,imag,taps,inverse,sum);"""
    src = replace(src, marker, block)
    src = replace(
        src,
        "w->support[epoch]>0 ?",
        "w->support[epoch]>0 &&\n            !(w->scout_stride && (f&1)) ?",
        count=2,
    )
    marker = "    return 0;\n}\n\n#pragma GCC pop_options"
    return replace(
        src, marker, "    if (w->scout_stride) return scout_stride_neighbors(w,count);\n" + marker
    )


def native(source):
    marker = "        size_t offset=(size_t)start_ms*context->rate/1000u;"
    return replace(
        source,
        marker,
        """        context->search->scout_stride=wide && context->receiver_count==2 &&
            context->refinement_mode==3 && context->search->regional_count<=12;
"""
        + marker,
    )


def apply(source):
    changed = {
        "native_glrt.c": native,
        "kernel/private/native_presence/presence.c": presence,
        "kernel/private/native_presence/coarse_fp32.h": coarse,
    }
    for name, transform in changed.items():
        path = source / name
        path.write_text(transform(path.read_text()))
    target = source / "kernel/private/native_presence" / HEADER.name
    target.write_bytes(HEADER.read_bytes())
