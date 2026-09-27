#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdatomic.h>

#if defined(__x86_64__) || defined(__i386__)
#include <cpuid.h>
#include <immintrin.h>
#endif

static _Thread_local int server_force_mode=-1;
static atomic_int server_hardware_state=ATOMIC_VAR_INIT(0);

static int server_simd_hardware(void)
{
#if defined(__x86_64__) || defined(__i386__)
    int state=atomic_load_explicit(&server_hardware_state,memory_order_acquire);
    if (!state) {
        unsigned int eax=0,ebx=0,ecx=0,edx=0;
        int available=__get_cpuid(1,&eax,&ebx,&ecx,&edx) &&
            (ecx&bit_SSSE3) && (ecx&bit_SSE4_1);
        int desired=available ? 2 : 1, expected=0;
        atomic_compare_exchange_strong_explicit(&server_hardware_state,&expected,desired,
            memory_order_release,memory_order_acquire);
        state=atomic_load_explicit(&server_hardware_state,memory_order_acquire);
    }
    return state==2;
#else
    return 0;
#endif
}

static int server_simd_enabled(void)
{
    return server_force_mode==0 ? 0 : server_simd_hardware();
}

int leo_server_simd_force(int mode)
{
    if (mode < -1 || mode > 1 || (mode==1 && !server_simd_hardware())) return -1;
    server_force_mode=mode;
    return 0;
}

const char *leo_server_simd_kernel(void)
{
    if (server_force_mode==0) return "scalar-forced";
    return server_simd_hardware() ?
        (server_force_mode==1 ? "ssse3-sse4.1-forced" : "ssse3-sse4.1-auto") :
        "scalar-hardware-fallback";
}

/* Pull in the frozen V4 ABI and science. The build places a deterministic copy
 * of pinned deployment presence.c ahead of deployment include paths; only its
 * CI16 fold/lag headers resolve to this directory's exact SIMD extensions. */
#include "blind_strided_v4.c"
#include "server_simd.h"

#if defined(__x86_64__) || defined(__i386__)
__attribute__((target("sse2")))
static inline __m128i server_select_four_complex(const int16_t *raw,
    uint32_t receiver)
{
    /* Both loads begin at RX0 I on physical sample boundaries and consume
     * exactly four complete dual-RX samples. RX1 is selected after loading. */
    __m128i first=_mm_loadu_si128((const __m128i *)raw);
    __m128i second=_mm_loadu_si128((const __m128i *)(raw+8));
    __m128i selected_first=receiver ?
        _mm_shuffle_epi32(first,_MM_SHUFFLE(3,1,3,1)) :
        _mm_shuffle_epi32(first,_MM_SHUFFLE(2,0,2,0));
    __m128i selected_second=receiver ?
        _mm_shuffle_epi32(second,_MM_SHUFFLE(3,1,3,1)) :
        _mm_shuffle_epi32(second,_MM_SHUFFLE(2,0,2,0));
    return _mm_unpacklo_epi64(selected_first,selected_second);
}

__attribute__((target("ssse3,sse4.1")))
static inline void server_rank_fold_four(const int16_t *a_raw, const int16_t *b_raw,
    uint32_t receiver, int64_t *sum_real, int64_t *sum_imag)
{
    __m128i a=server_select_four_complex(a_raw,receiver);
    __m128i b=server_select_four_complex(b_raw,receiver);
    __m128i ar=server_deinterleave_real32(a), ai=server_deinterleave_imag32(a);
    __m128i br=server_deinterleave_real32(b), bi=server_deinterleave_imag32(b);
    server_add_widened_pair(sum_real,_mm_mullo_epi32(ar,br),_mm_mullo_epi32(ai,bi),0);
    server_add_widened_pair(sum_imag,_mm_mullo_epi32(ar,bi),_mm_mullo_epi32(ai,br),1);
}

__attribute__((target("sse2")))
static void server_pack_simd(const int16_t *raw, int16_t *packed, size_t count,
    uint32_t receiver)
{
    size_t sample=0;
    for (; sample+3<count; sample+=4) {
        __m128i selected=server_select_four_complex(raw+4*sample,receiver);
        _mm_storeu_si128((__m128i *)(packed+2*sample),selected);
    }
    for (; sample<count; ++sample) {
        packed[2*sample]=raw[4*sample+2*receiver];
        packed[2*sample+1]=raw[4*sample+2*receiver+1];
    }
}
#endif

static void server_pack(const int16_t *raw, int16_t *packed, size_t count,
    uint32_t receiver)
{
#if defined(__x86_64__) || defined(__i386__)
    if (server_simd_enabled()) {
        server_pack_simd(raw,packed,count,receiver);
        return;
    }
#endif
    for (size_t sample=0; sample<count; ++sample) {
        packed[2*sample]=raw[4*sample+2*receiver];
        packed[2*sample+1]=raw[4*sample+2*receiver+1];
    }
}

int leo_server_simd_pack_probe(const int16_t *raw, size_t count,
    uint32_t receiver, int16_t *packed)
{
    if (!raw || !packed || !count || receiver>1) return -1;
    server_pack(raw,packed,count,receiver);
    return 0;
}

static void server_rank_fold(leo_presence_rank_workspace *w, const int16_t *raw,
    uint32_t receiver)
{
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
            size_t k=block, stop=valid;
#else
            for (size_t group=first_group; group<group_cursor; ++group) {
            size_t k=w->groups[group];
            size_t stop=k+4<valid ? k+4 : valid;
#endif
#if defined(__x86_64__) || defined(__i386__)
            if (server_simd_enabled()) for (; k+3<stop; k+=4) {
                /* b consumes through k+7. k+3<valid with valid=window-start-4
                 * proves the final complete dual-RX sample stays in-window. */
                server_rank_fold_four(raw+4*(start+k),raw+4*(start+k+4),receiver,
                    w->sum_real+k,w->sum_imag+k);
            }
#endif
            for (; k<stop; ++k) {
                size_t offset=4*(start+k)+2*receiver;
                int64_t ar=raw[offset], ai=raw[offset+1];
                int64_t br=raw[offset+16], bi=raw[offset+17];
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

static int server_rank_window(leo_presence_rank_workspace *w, const int16_t *raw,
    size_t count, uint32_t receiver, leo_presence_timing_proposal *result)
{
    if (w) w->have_screens=0;
    if (!w || !raw || !result || count!=w->window || receiver>1 ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_presence_timing_proposal out={0};
    double cpu=rank_clock(CLOCK_PROCESS_CPUTIME_ID), wall=rank_clock(CLOCK_MONOTONIC);
    double started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
    server_rank_fold(w,raw,receiver);
    out.fold_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
    if (correlate(w,0,&out)) return -1;
    out.correlation_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    out.total_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out.total_wall_ms=rank_clock(CLOCK_MONOTONIC)-wall;
    *result=out;
    return 0;
}

static int server_rank(leo_presence_rank_workspace *w, const int16_t *raw,
    size_t count, uint32_t receiver, leo_presence_rank_result *result)
{
    if (w) w->have_screens=0;
    if (!w || !raw || !result || count!=6*w->window || receiver>1 ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_presence_rank_result out={0};
    leo_presence_rank_screens screens={0};
    double cpu=rank_clock(CLOCK_PROCESS_CPUTIME_ID), wall=rank_clock(CLOCK_MONOTONIC);
    for (size_t slice=0; slice<6; ++slice) {
        double started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
        server_rank_fold(w,raw+4*slice*w->window,receiver);
        out.fold_cpu_ms+=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
        started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
        for (size_t projection=0; projection<PROJECTION_COUNT; ++projection) {
            size_t row=LEO_PRESENCE_RANK_AREA_PROJECTION+projection;
            leo_presence_timing_proposal timing={0};
            if (correlate(w,projection,&timing)) return -1;
            screens.available_mask|=1u<<row;
            screens.scores[row][slice]=timing.score;
            screens.epochs[row][slice]=timing.epoch;
            uint32_t *order=screens.order[row];
            order[slice]=(uint32_t)slice;
            for (size_t j=slice; j>0 && screens.scores[row][order[j]]>
                screens.scores[row][order[j-1]]; --j) {
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
    memcpy(out.projected_epoch_samples,screens.epochs[screens.selected],
        sizeof(out.projected_epoch_samples));
    out.total_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out.total_wall_ms=rank_clock(CLOCK_MONOTONIC)-wall;
    *result=out;
    w->screens=screens;
    w->have_screens=1;
    return 0;
}

leo_server_simd_workspace *leo_server_simd_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t n, uint32_t screen_bins, uint32_t timing_bins)
{
    return leo_blind_strided_v4_create(rate,exact,control,n,screen_bins,timing_bins);
}

void leo_server_simd_destroy(leo_server_simd_workspace *w)
{
    leo_blind_strided_v4_destroy(w);
}

int leo_server_simd_run_ci16(leo_server_simd_workspace *w,
    const int16_t *raw, size_t count, uint32_t receiver, uint32_t maximum,
    uint32_t seeded, leo_presence_dwell_result *out)
{
    if (!w || !w->dwell || !raw || !out || count!=6*w->window || receiver>1 ||
        !maximum || maximum>6 || seeded>1) return -1;
    leo_presence_dwell_result result={0};
    double cpu=dwell_clock(CLOCK_PROCESS_CPUTIME_ID), wall=dwell_clock(CLOCK_MONOTONIC);
    if (server_rank(w->dwell->rank,raw,count,receiver,&result.rank)) return -1;
    for (uint32_t k=0; k<maximum; ++k) {
        uint32_t index=result.rank.order[k];
        const int16_t *samples=raw+4*index*w->window;
        uint32_t epoch=result.rank.projected_epoch_samples[index];
        if (seeded && w->dwell->timing) {
            if (server_rank_window(w->dwell->timing,samples,w->window,receiver,
                &result.timing_proposals[k])) return -1;
            epoch=result.timing_proposals[k].epoch;
        }
        server_pack(samples,w->selected,w->window,receiver);
        int status=seeded ? leo_presence_confirm_ci16(w->dwell->confirm,w->selected,
            w->window,(int32_t)epoch,&result.confirmations[k]) :
            leo_presence_run_ci16(w->dwell->confirm,w->selected,w->window,
                &result.confirmations[k]);
        if (status || leo_presence_get_nuisance(w->dwell->confirm,
            &result.nuisances[k])) return -1;
        result.confirmation_window_mask|=1u<<index;
        ++result.confirmation_count;
        result.prefix_cpu_ms[k]=dwell_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
        result.prefix_wall_ms[k]=dwell_clock(CLOCK_MONOTONIC)-wall;
    }
    result.total_cpu_ms=dwell_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    result.total_wall_ms=dwell_clock(CLOCK_MONOTONIC)-wall;
    *out=result;
    return 0;
}

int leo_server_simd_get_screens(const leo_server_simd_workspace *w,
    leo_presence_rank_screens *screens)
{
    return w && w->dwell ? leo_presence_rank_get_screens(w->dwell->rank,screens) : -1;
}
