#define _POSIX_C_SOURCE 200809L
#include "window_rank.h"
#include <complex.h>
#include <fenv.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifndef LEO_PRESENCE_RANK_AREA_PROJECTION
#define LEO_PRESENCE_RANK_AREA_PROJECTION 0
#endif
#ifndef LEO_PRESENCE_RANK_HYBRID_PROJECTION
#define LEO_PRESENCE_RANK_HYBRID_PROJECTION 0
#endif
#if LEO_PRESENCE_RANK_AREA_PROJECTION != 0 && LEO_PRESENCE_RANK_AREA_PROJECTION != 1
#error "LEO_PRESENCE_RANK_AREA_PROJECTION must be 0 or 1"
#endif
#if LEO_PRESENCE_RANK_HYBRID_PROJECTION != 0 && LEO_PRESENCE_RANK_HYBRID_PROJECTION != 1
#error "LEO_PRESENCE_RANK_HYBRID_PROJECTION must be 0 or 1"
#endif
#if LEO_PRESENCE_RANK_HYBRID_PROJECTION && LEO_PRESENCE_RANK_AREA_PROJECTION
#error "select either hybrid or area-only projection"
#endif
#define PROJECTION_COUNT (1+LEO_PRESENCE_RANK_HYBRID_PROJECTION)
#if defined(LEO_PRESENCE_RANK_ALL_CELLS) || LEO_PRESENCE_RANK_AREA_PROJECTION || LEO_PRESENCE_RANK_HYBRID_PROJECTION
#define RANK_FULL_FOLD 1
#else
#define RANK_FULL_FOLD 0
#endif
#if defined(__ARM_NEON) && !defined(LEO_PRESENCE_RANK_FORCE_SCALAR)
#include <arm_neon.h>
#endif

/* This separate experiment uses FP32 only for the proposal FFT. CI16 lag
 * products/sums are exact int64; normalization is FP64. No final GLRT,
 * fractional interpolation, sample counters, or existing kernels change. */
typedef struct {
    size_t first, limit;
    double first_weight, last_weight, width;
} rank_area;

struct leo_presence_rank_workspace {
    uint32_t rate, bins;
    size_t n, window;
    float complex *roots, *input, *output, *template_fft;
    double complex *folded;
    double complex *projected;
    rank_area *areas;
    int64_t *sum_real, *sum_imag;
    uint32_t *support, starts[15];
    uint32_t *groups;
    unsigned char *needed;
    size_t group_count;
    leo_presence_rank_screens screens;
    int have_screens;
};

static double rank_clock(clockid_t id)
{
    struct timespec ts;
    if (clock_gettime(id,&ts)) return 0;
    return ts.tv_sec*1000.0+ts.tv_nsec/1e6;
}

static void rank_fft(leo_presence_rank_workspace *w)
{
    const size_t n=w->bins;
    for (size_t i=0, reversed=0; i<n; ++i) {
        w->output[reversed]=w->input[i];
        size_t bit=n>>1;
        while (bit && (reversed&bit)) { reversed^=bit; bit>>=1; }
        reversed^=bit;
    }
    for (size_t width=2, stride=n>>1; width<=n; width<<=1, stride>>=1) {
        size_t half=width>>1;
        for (size_t base=0; base<n; base+=width) {
            for (size_t k=0; k<half; ++k) {
                float complex even=w->output[base+k];
                float complex odd=w->output[base+half+k]*w->roots[k*stride];
                w->output[base+k]=even+odd;
                w->output[base+half+k]=even-odd;
            }
        }
    }
}

/* Circular interpolation is deliberately a proposal approximation, not a
 * claim of lossless decimation. Its sensitivity must be measured per grid.
 * Center in FP64 first so a pure constant lag sequence remains exactly zero. */
static double complex projection_cell(leo_presence_rank_workspace *w, size_t k, int area)
{
    if (area) {
    /* Integrate piecewise-constant native cells over each output-bin area.
     * This is a separately qualified smoothing/resampling statistic, not an
     * exact optimization or an ideal brick-wall antialias filter. */
    const rank_area *geometry=&w->areas[k];
    double complex value=0;
    for (size_t cell=geometry->first; cell<geometry->limit; ++cell) {
        double weight=cell==geometry->first ? geometry->first_weight :
            (cell+1==geometry->limit ? geometry->last_weight : 1.0);
        value+=weight*w->folded[cell];
    }
    return value/geometry->width;
    }
    double position=(double)k*w->n/w->bins;
    size_t left=(size_t)position, right=left+1==w->n ? 0 : left+1;
    return w->folded[left]+(position-left)*(w->folded[right]-w->folded[left]);
}

static int project(leo_presence_rank_workspace *w, int area)
{
    double complex mean=0;
    for (size_t k=0; k<w->bins; ++k) {
        w->projected[k]=projection_cell(w,k,area);
        mean+=w->projected[k];
    }
    mean/=w->bins;
    double energy=0;
    for (size_t k=0; k<w->bins; ++k) {
        double complex value=w->projected[k]-mean;
        w->input[k]=(float)creal(value)+I*(float)cimag(value);
        energy+=creal(value)*creal(value)+cimag(value)*cimag(value);
    }
    if (energy==0) { memset(w->input,0,w->bins*sizeof(*w->input)); return 0; }
    float scale=(float)(1/sqrt(energy));
    if (!isfinite(energy) || !isfinite(scale) || scale==0) return -1;
    for (size_t k=0; k<w->bins; ++k) w->input[k]*=scale;
    return 1;
}

void leo_presence_rank_destroy(leo_presence_rank_workspace *w)
{
    if (!w) return;
    free(w->roots); free(w->input); free(w->output); free(w->template_fft);
    free(w->folded); free(w->sum_real); free(w->sum_imag); free(w->support);
    free(w->projected); free(w->areas);
    free(w->groups); free(w->needed);
    free(w);
}

leo_presence_rank_workspace *leo_presence_rank_create(uint32_t rate,
    const leo_presence_complex *exact, size_t n, uint32_t bins)
{
    if (fegetround()!=FE_TONEAREST || (rate!=2500000 && rate!=5000000) || !exact ||
        n!=(size_t)nearbyint(rate/750.0) || bins<512 || bins>8192 || (bins&(bins-1))) return NULL;
    for (size_t k=0; k<n; ++k)
        if (!isfinite(exact[k].re) || !isfinite(exact[k].im) ||
            fabs(exact[k].re)>16 || fabs(exact[k].im)>16) return NULL;
    leo_presence_rank_workspace *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->rate=rate; w->n=n; w->window=rate/50; w->bins=bins;
#define ALLOC(field, count) do { \
    w->field=calloc(count,sizeof(*w->field)); \
    if (!w->field) { leo_presence_rank_destroy(w); return NULL; } \
} while (0)
    ALLOC(roots,bins); ALLOC(input,bins); ALLOC(output,bins);
    ALLOC(template_fft,bins*PROJECTION_COUNT);
    ALLOC(projected,bins);
#if LEO_PRESENCE_RANK_AREA_PROJECTION || LEO_PRESENCE_RANK_HYBRID_PROJECTION
    ALLOC(areas,bins);
    /* Freeze the exact piecewise-constant overlap geometry at setup. Runtime
     * sums retain the same cell order, weights, and normalization as the
     * explicit fmin/fmax integral, including bins narrower than one cell. */
    for (size_t k=0; k<bins; ++k) {
        double begin=(double)k*n/bins, end=(double)(k+1)*n/bins;
        rank_area *g=&w->areas[k];
        g->first=(size_t)begin; g->limit=(size_t)ceil(end);
        g->first_weight=fmin(end,(double)(g->first+1))-begin;
        g->last_weight=end-fmax(begin,(double)(g->limit-1));
        g->width=end-begin;
    }
#endif
    ALLOC(folded,n); ALLOC(sum_real,n); ALLOC(sum_imag,n); ALLOC(support,n);
    ALLOC(groups,(n+3)/4); ALLOC(needed,n);
#undef ALLOC
    /* project() reads only the two interpolation cells for each output bin.
     * Retain precisely those dependencies; full-cell folding followed by
     * projection discarded the other sums. This does not change the screen's
     * statistic, frame support, or approximation grid. SIMD groups may include
     * extra adjacent cells, but normalization is needed only for dependencies. */
    for (size_t k=0; k<bins; ++k) {
        size_t left=(size_t)((double)k*n/bins), right=left+1==n ? 0 : left+1;
        w->needed[left]=w->needed[right]=1;
    }
#if RANK_FULL_FOLD
    /* Qualification comparator for dependency pruning, not a new statistic. */
    memset(w->needed,1,n);
#endif
    for (size_t k=0; k<n; k+=4) {
        int needed=0;
        for (size_t j=k; j<k+4 && j<n; ++j) needed|=w->needed[j];
        if (needed) w->groups[w->group_count++]=(uint32_t)k;
    }
    for (size_t frame=0; frame<15; ++frame)
        w->starts[frame]=(uint32_t)nearbyint(frame*(rate/750.0));
    for (size_t frame=0; frame<15; ++frame) {
        size_t valid=w->window-w->starts[frame]-4;
        if (valid>w->n) valid=w->n;
        for (size_t k=0; k<valid; ++k) ++w->support[k];
    }
    for (size_t k=0; k<bins; ++k) {
        double angle=-6.283185307179586476925286766559*k/bins;
        w->roots[k]=(float)cos(angle)+I*(float)sin(angle);
    }
    for (size_t k=0; k<n; ++k) {
        size_t next=(k+4)%n;
        w->folded[k]=(exact[next].re+I*exact[next].im)*(exact[k].re-I*exact[k].im);
    }
    for (size_t projection=0; projection<PROJECTION_COUNT; ++projection) {
        if (project(w,LEO_PRESENCE_RANK_AREA_PROJECTION+(int)projection)<=0) {
            leo_presence_rank_destroy(w); return NULL;
        }
        rank_fft(w);
        memcpy(w->template_fft+projection*bins,w->output,bins*sizeof(*w->output));
    }
    return w;
}

static void fold(leo_presence_rank_workspace *w, const int16_t *iq)
{
    /* Keep a small set of folded cells hot while traversing all frame starts.
     * Each cell still accumulates the same exact integer terms in frame order.
     * The whole-frame arrays exceed Cortex-A9 L1 at both rates. */
#if !RANK_FULL_FOLD
    size_t group_cursor=0;
#endif
    for (size_t block=0; block<w->n; block+=256) {
    size_t end=block+256<w->n ? block+256 : w->n;
#if !RANK_FULL_FOLD
    size_t first_group=group_cursor;
    while (group_cursor<w->group_count && w->groups[group_cursor]<end) ++group_cursor;
#endif
    memset(w->sum_real+block,0,(end-block)*sizeof(*w->sum_real));
    memset(w->sum_imag+block,0,(end-block)*sizeof(*w->sum_imag));
    for (size_t frame=0; frame<15; ++frame) {
        size_t start=w->starts[frame], valid=w->window-start-4;
        if (valid>end) valid=end;
#if RANK_FULL_FOLD
        /* Dense projections consume every cell. Traverse directly instead of
         * loading a redundant group-index vector and testing four-cell tails
         * at every group. Products and accumulation order remain identical. */
        size_t k=block, stop=valid;
#else
        for (size_t group=first_group; group<group_cursor; ++group) {
        size_t k=w->groups[group];
        size_t stop=k+4<valid ? k+4 : valid;
#endif
#if defined(__ARM_NEON) && !defined(LEO_PRESENCE_RANK_FORCE_SCALAR)
        /* Widen EACH product before adding/subtracting: CI16 extrema exceed
         * int32 in a complex product. Four independent folded cells retain
         * exact int64 accumulation and the scalar support geometry. */
#if RANK_FULL_FOLD
        for (; k+3<valid; k+=4) {
#else
        if (k+3<valid) {
#endif
            int16x4x2_t a=vld2_s16(iq+2*(start+k));
            int16x4x2_t b=vld2_s16(iq+2*(start+k+4));
            int32x4_t rr=vmull_s16(a.val[0],b.val[0]);
            int32x4_t ii=vmull_s16(a.val[1],b.val[1]);
            int32x4_t ri=vmull_s16(a.val[0],b.val[1]);
            int32x4_t ir=vmull_s16(a.val[1],b.val[0]);
            int64x2_t re0=vaddq_s64(vmovl_s32(vget_low_s32(rr)),vmovl_s32(vget_low_s32(ii)));
            int64x2_t re1=vaddq_s64(vmovl_s32(vget_high_s32(rr)),vmovl_s32(vget_high_s32(ii)));
            int64x2_t im0=vsubq_s64(vmovl_s32(vget_low_s32(ri)),vmovl_s32(vget_low_s32(ir)));
            int64x2_t im1=vsubq_s64(vmovl_s32(vget_high_s32(ri)),vmovl_s32(vget_high_s32(ir)));
            vst1q_s64(w->sum_real+k,vaddq_s64(vld1q_s64(w->sum_real+k),re0));
            vst1q_s64(w->sum_real+k+2,vaddq_s64(vld1q_s64(w->sum_real+k+2),re1));
            vst1q_s64(w->sum_imag+k,vaddq_s64(vld1q_s64(w->sum_imag+k),im0));
            vst1q_s64(w->sum_imag+k+2,vaddq_s64(vld1q_s64(w->sum_imag+k+2),im1));
#if !RANK_FULL_FOLD
            k+=4;
#endif
        }
#endif
        for (; k<stop; ++k) {
            size_t offset=2*(start+k);
            int64_t ar=iq[offset], ai=iq[offset+1];
            int64_t br=iq[offset+8], bi=iq[offset+9];
            w->sum_real[k]+=ar*br+ai*bi;
            w->sum_imag[k]+=ar*bi-ai*br;
        }
#if !RANK_FULL_FOLD
        }
#endif
    }
    }
    for (size_t k=0; k<w->n; ++k) {
        if (!w->needed[k]) continue;
        double support=w->support[k] ? w->support[k] : 1;
        w->folded[k]=(double)w->sum_real[k]/support+I*((double)w->sum_imag[k]/support);
    }
}

static int correlate(leo_presence_rank_workspace *w, size_t projection,
    leo_presence_timing_proposal *out)
{
        int projected=project(w,LEO_PRESENCE_RANK_AREA_PROJECTION+(int)projection);
        if (projected<0) return -1;
        if (projected) {
            rank_fft(w);
            for (size_t k=0; k<w->bins; ++k)
                w->input[k]=conjf(w->output[k]*conjf(w->template_fft[projection*w->bins+k]));
            rank_fft(w);
            size_t best=0;
            double value=-1;
            for (size_t k=0; k<w->bins; ++k) {
                double re=crealf(w->output[k]), im=cimagf(w->output[k]);
                double score=re*re+im*im;
                if (score>value) { value=score; best=k; }
            }
            out->score=sqrt(value)/w->bins;
            out->epoch=(uint32_t)nearbyint((double)best*w->n/w->bins)%w->n;
        }
    return 0;
}

int leo_presence_rank_window_ci16(leo_presence_rank_workspace *w, const int16_t *iq,
    size_t count, leo_presence_timing_proposal *result)
{
    if (w) w->have_screens=0;
    if (!w || !iq || !result || count!=w->window || fegetround()!=FE_TONEAREST) return -1;
    leo_presence_timing_proposal out={0};
    double cpu=rank_clock(CLOCK_PROCESS_CPUTIME_ID), wall=rank_clock(CLOCK_MONOTONIC);
    double started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
    fold(w,iq);
    out.fold_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
    if (correlate(w,0,&out)) return -1;
    out.correlation_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    out.total_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out.total_wall_ms=rank_clock(CLOCK_MONOTONIC)-wall;
    *result=out;
    return 0;
}

int leo_presence_rank_ci16(leo_presence_rank_workspace *w, const int16_t *iq,
    size_t count, leo_presence_rank_result *result)
{
    if (w) w->have_screens=0;
    if (!w || !iq || !result || count!=6*w->window || fegetround()!=FE_TONEAREST) return -1;
    leo_presence_rank_result out={0};
    leo_presence_rank_screens screens={0};
    double cpu=rank_clock(CLOCK_PROCESS_CPUTIME_ID), wall=rank_clock(CLOCK_MONOTONIC);
    for (size_t slice=0; slice<6; ++slice) {
        double started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
        fold(w,iq+2*slice*w->window);
        out.fold_cpu_ms+=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
        started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
        /* Both proposals share the exact full-cell fold. Neither gets a
         * separate pass over IQ; only projection/correlation are repeated. */
        for (size_t projection=0; projection<PROJECTION_COUNT; ++projection) {
            size_t row=LEO_PRESENCE_RANK_AREA_PROJECTION+projection;
            leo_presence_timing_proposal timing={0};
            if (correlate(w,projection,&timing)) return -1;
            screens.available_mask|=1u<<row;
            screens.scores[row][slice]=timing.score;
            screens.epochs[row][slice]=timing.epoch;
            uint32_t *order=screens.order[row];
            order[slice]=(uint32_t)slice;
            for (size_t j=slice; j>0 && screens.scores[row][order[j]]>screens.scores[row][order[j-1]]; --j) {
                uint32_t swap=order[j]; order[j]=order[j-1]; order[j-1]=swap;
            }
        }
        out.correlation_cpu_ms+=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    }
    screens.selected=LEO_PRESENCE_RANK_AREA_PROJECTION;
    for (size_t row=0; row<2; ++row) if (screens.available_mask&(1u<<row))
        screens.contrast[row]=screens.scores[row][screens.order[row][0]] /
            fmax(screens.scores[row][screens.order[row][1]],1e-30);
    if (LEO_PRESENCE_RANK_HYBRID_PROJECTION && screens.contrast[1]>screens.contrast[0])
        screens.selected=1;
    memcpy(out.scores,screens.scores[screens.selected],sizeof(out.scores));
    memcpy(out.order,screens.order[screens.selected],sizeof(out.order));
    memcpy(out.projected_epoch_samples,screens.epochs[screens.selected],sizeof(out.projected_epoch_samples));
    out.total_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out.total_wall_ms=rank_clock(CLOCK_MONOTONIC)-wall;
    *result=out;
    w->screens=screens;
    w->have_screens=1;
    return 0;
}

int leo_presence_rank_get_screens(const leo_presence_rank_workspace *w,
    leo_presence_rank_screens *screens)
{
    if (!w || !screens || !w->have_screens) return -1;
    *screens=w->screens;
    return 0;
}
