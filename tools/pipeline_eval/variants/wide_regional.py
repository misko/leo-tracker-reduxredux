"""Width-only extension of the prepared-fractional wave8 release for 10 MS/s visits."""

from pathlib import Path

HEADER = Path(__file__).with_name("wide_regional_cfo.h")


def replace(source, old, new, *, count=1):
    if source.count(old) != count:
        raise ValueError(f"Wide regional source binding changed at {old!r}")
    return source.replace(old, new)


def presence(source):
    source = replace(
        source,
        "#define CFO_COUNT 12",
        """#define CFO_COUNT 24
#define ORDINARY_REGIONAL_BINS 11
#define WIDE_REGIONAL_BINS 21
#define REGIONAL_CFO_STEP 80000.0
#define WIDE_REGIONAL_CFO_LIMIT 800000.0
#define ORDINARY_REGIONAL_CFO_LIMIT 400000.0
#define REGIONAL_NARROW_OFFSET ((WIDE_REGIONAL_BINS-ORDINARY_REGIONAL_BINS)/2)
_Static_assert(CFO_COUNT>=WIDE_REGIONAL_BINS && CFO_COUNT%4==0,
    "Four-lane regional storage must cover all physical CFO bins");""",
    )
    source = replace(source, "    int regional_count;", "    int regional_count, wide_regional;")
    source = replace(
        source,
        "double frequencies[12], correlation_real[12], correlation_imag[12];",
        "double frequencies[CFO_COUNT], correlation_real[CFO_COUNT], correlation_imag[CFO_COUNT];",
    )
    source = replace(source, "[12*45*12]", "[12*45*CFO_COUNT]", count=2)
    marker = "static double clock_ms(clockid_t id)"
    methods = """static int regional_cfo_bins(const leo_presence_workspace *w)
{
    return w->wide_regional ? WIDE_REGIONAL_BINS : ORDINARY_REGIONAL_BINS;
}

static double regional_cfo_limit(const leo_presence_workspace *w)
{
    return w->wide_regional ? WIDE_REGIONAL_CFO_LIMIT : ORDINARY_REGIONAL_CFO_LIMIT;
}

static void regional_cfo_band(leo_presence_workspace *w, int wide)
{
    w->wide_regional=wide;
    for (int f=0;f<regional_cfo_bins(w);++f)
        w->frequencies[f]=-regional_cfo_limit(w)+REGIONAL_CFO_STEP*f;
}

"""
    source = replace(source, marker, methods + marker)
    source = replace(source, "        w->frequencies[k] = -400000.0 + k * 80000.0;\n", "")
    source = replace(
        source,
        "    for (int k = 0; k < 16; ++k)\n        w->offsets[k]",
        "    regional_cfo_band(w,0);\n    for (int k = 0; k < 16; ++k)\n        w->offsets[k]",
    )
    begin = source.index("/* The research reference adapter widens")
    end = source.index("static int glrt(", begin)
    source = source[:begin] + source[end:]
    source = replace(
        source, "fabs(cfo)>leo_presence_glrt_cfo_limit_hz", "fabs(cfo)>regional_cfo_limit(w)"
    )
    # The stand-alone presence API retains its original narrow width. A wider
    # regional mode is only selected by the release native short-window path.
    return source


def coarse(source):
    source = replace(source, "real+12*k+4*lane", "real+CFO_COUNT*k+4*lane")
    source = replace(source, "imag+12*k+4*lane", "imag+CFO_COUNT*k+4*lane")
    source = replace(source, "real[12*k+f]", "real[CFO_COUNT*k+f]", count=2)
    source = replace(source, "imag[12*k+f]", "imag[CFO_COUNT*k+f]", count=2)
    source = replace(
        source,
        "static void coarse_fp32_templates",
        '#include "wide_regional_cfo.h"\n\nstatic void coarse_fp32_templates',
    )
    source = replace(
        source,
        "double angle=TAU*w->frequencies[f]*k/w->rate;",
        "double cfo=-WIDE_REGIONAL_CFO_LIMIT+REGIONAL_CFO_STEP*f;\n"
        "                double angle=TAU*cfo*k/w->rate;",
    )
    source = replace(source, "symbol*45*12+12*k+f", "symbol*45*CFO_COUNT+CFO_COUNT*k+f")
    stock = """        coarse_float_add(w->float_samples+2*position,
            w->float_reference_real+symbol*45*12, w->float_reference_imag+symbol*45*12,
            taps,inverse,w->float_accumulated+12*epoch);"""
    candidate = """        int first=symbol*45*CFO_COUNT;
        if (!w->wide_regional) first+=REGIONAL_NARROW_OFFSET;
        const float *samples=w->float_samples+2*position;
        const float *real=w->float_reference_real+first, *imag=w->float_reference_imag+first;
        float *sum=w->float_accumulated+CFO_COUNT*epoch;
        if (w->wide_regional) wide_regional_float_add(samples,real,imag,taps,inverse,sum);
        else coarse_float_add(samples,real,imag,taps,inverse,sum);"""
    source = replace(source, stock, candidate)
    source = replace(
        source,
        "w->float_accumulated[12*epoch+f]",
        "w->float_accumulated[CFO_COUNT*epoch+f]",
        count=2,
    )
    source = replace(
        source,
        "    for (int f=0; f<CFO_COUNT; ++f)\n",
        "    for (int f=0; f<regional_cfo_bins(w); ++f)\n",
        count=2,
    )
    return source


def full_search(source):
    source = replace(source, "coarse_cfo_hz[11]", "*coarse_cfo_hz", count=3)
    source = replace(source, "for(int f=0;f<11;++f)", "for(int f=0;f<regional_cfo_bins(w);++f)")
    source = replace(
        source, "11*(size_t)regional_count", "regional_cfo_bins(w)*(size_t)regional_count"
    )
    source = replace(source, "fmax(-400000,", "fmax(-regional_cfo_limit(w),", count=3)
    return replace(source, "fmin(400000,", "fmin(regional_cfo_limit(w),", count=3)


def native_glrt(source):
    marker = "    double started=0,finished=0,stage_cpu=0,stage_wall=0,end_cpu=0,end_wall=0;"
    return replace(
        source,
        marker,
        "    int wide=short_window&&context->rate==10000000u;\n"
        "    if (context->search->wide_regional!=wide)\n"
        "        regional_cfo_band(context->search,wide);\n" + marker,
    )
