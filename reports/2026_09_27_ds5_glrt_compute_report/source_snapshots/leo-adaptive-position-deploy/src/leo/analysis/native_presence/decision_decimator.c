#include "decision_decimator.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
#if defined(LEO_DECIMATOR_FFT)
#include "decision_decimator_fft.h"
#endif
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif

#define MAX_TAPS 257
#ifndef LEO_DECIMATOR_TILE
#define LEO_DECIMATOR_TILE 2048
#endif
#define TILE LEO_DECIMATOR_TILE
#if TILE!=1024 && TILE!=2048
#error "unsupported decimator tile"
#endif
struct fir { int16_t h[MAX_TAPS]; float fp[MAX_TAPS]; unsigned offset[MAX_TAPS], used, count, kernel; };
#if defined(__ARM_NEON) && defined(LEO_DECIMATOR_COMPACT)
#include "decision_decimator_compact.inc"
#endif
struct leo_decimator {
    struct fir a,b;
    size_t count;
    int16_t *source, *middle;
    float *prefiltered, denominator[8], state[4][2][2];
    int recursive;
    unsigned factor;
#if defined(LEO_DECIMATOR_FFT)
    leo_decimator_fft *fast;
#endif
};

static int configure(struct fir *f, const int16_t *h, unsigned n)
{
    if (!h || !n || n>MAX_TAPS || !(n&1)) return -1;
    int sum=0, absolute=0;
    for (unsigned k=0;k<n;++k) {
        if (h[k]!=h[n-1-k]) return -1;
        sum+=h[k]; absolute+=abs(h[k]);
        if (h[k]) {
            f->h[f->used]=h[k]; f->fp[f->used]=h[k]/32768.0f;
            f->offset[f->used++]=k;
        }
    }
    if (sum!=32768 || absolute>=65536) return -1;
    f->count=n;
#if defined(__ARM_NEON) && defined(LEO_DECIMATOR_COMPACT)
    if (n==15 && !memcmp(h,compact_coefficients_15,2*n)) f->kernel=15;
    if (n==47 && !memcmp(h,compact_coefficients_47,2*n)) f->kernel=47;
#endif
    return 0;
}

leo_decimator *leo_decimator_create(const int16_t *h1, unsigned n1,
    const int16_t *h2, unsigned n2, size_t count)
{
    if (!count || count>1200000 || count%4) return NULL;
    leo_decimator *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    if ((n1 && configure(&w->a,h1,n1)) || configure(&w->b,h2,n2)) goto fail;
    w->count=count;
    w->factor=4;
#if defined(LEO_DECIMATOR_FFT)
    if (!n1) {
        w->fast=leo_decimator_fft_create(h2,n2,count);
        if (!w->fast) goto fail;
    }
#endif
    w->source=calloc(2*(TILE+MAX_TAPS+16),sizeof(int16_t));
    w->middle=calloc(2*(TILE/2+MAX_TAPS+16),sizeof(int16_t));
    if (!w->source || !w->middle) goto fail;
    return w;
fail:
    leo_decimator_destroy(w); return NULL;
}

leo_decimator *leo_decimator_create_factor(const int16_t *h, unsigned n,
    unsigned factor, size_t count)
{
    if (!count || count>2400000 || factor<2 || factor>8 || count%factor) return NULL;
    leo_decimator *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    if (configure(&w->b,h,n)) goto fail;
    w->count=count; w->factor=factor;
    /* The general path keeps one reset-prefixed source extent. This avoids
     * inventing phase at tile boundaries when factor does not divide TILE. */
    w->source=calloc(2*(count+MAX_TAPS+16),sizeof(int16_t));
    if (!w->source) goto fail;
    return w;
fail:
    leo_decimator_destroy(w); return NULL;
}

void leo_decimator_destroy(leo_decimator *w)
{
    if (!w) return;
#if defined(LEO_DECIMATOR_FFT)
    leo_decimator_fft_destroy(w->fast);
#endif
    free(w->source); free(w->middle); free(w->prefiltered); free(w);
}

leo_decimator *leo_decimator_create_recursive(const int16_t *h1, unsigned n1,
    const int16_t *numerator, unsigned n2, const float denominator[8], size_t count)
{
#if defined(LEO_DECIMATOR_FP32)
    /* The earlier approximate FIR experiment has a different output path. */
    (void)h1; (void)n1; (void)numerator; (void)n2; (void)denominator; (void)count;
    return NULL;
#else
    if (!n1 || !numerator || !n2 || n2>MAX_TAPS || !denominator ||
        !count || count>1200000 || count%4) return NULL;
    leo_decimator *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    if (configure(&w->a,h1,n1)) goto fail_recursive;
    int absolute=0;
    for (unsigned k=0;k<n2;++k) {
        absolute+=abs(numerator[k]);
        if (numerator[k]) {
            w->b.h[w->b.used]=numerator[k]; w->b.offset[w->b.used++]=k;
        }
    }
    if (!absolute || absolute>=65536) goto fail_recursive;
    for (unsigned k=0;k<4;++k) {
        float a=denominator[2*k],b=denominator[2*k+1];
        if (!isfinite(a) || !isfinite(b) || fabsf(b)>=.99f ||
            1+a+b<=.01f || 1-a+b<=.01f) goto fail_recursive;
    }
    w->b.count=n2; w->count=count; w->recursive=1;
    memcpy(w->denominator,denominator,sizeof(w->denominator));
    w->source=calloc(2*(TILE+MAX_TAPS+16),sizeof(int16_t));
    w->middle=calloc(2*(TILE/2+MAX_TAPS+16),sizeof(int16_t));
    w->prefiltered=calloc(TILE/2,sizeof(float));
    if (!w->source || !w->middle || !w->prefiltered) goto fail_recursive;
    return w;
fail_recursive:
    leo_decimator_destroy(w); return NULL;
#endif
}

static int16_t quantize(int32_t x)
{
    /* Portable floor division, matching NEON rounding shift, including ties. */
    int64_t y=(int64_t)x+16384;
    y=y>=0 ? y/32768 : -((-y+32767)/32768);
    return y>32767 ? 32767 : y< -32768 ? -32768 : (int16_t)y;
}

static void filter(const struct fir *f, const int16_t *x, size_t count,
    unsigned factor, int16_t *out, float *floating)
{
    size_t m=0, length=count/factor;
#if defined(__ARM_NEON)
    if (factor!=2 && factor!=4) {
        for (;m<length;++m) {
            int32_t re=0,im=0;
            for (unsigned k=0;k<f->used;++k) {
                ptrdiff_t p=2*((ptrdiff_t)(m*factor)-(ptrdiff_t)f->offset[k]);
                re+=(int32_t)x[p]*f->h[k]; im+=(int32_t)x[p+1]*f->h[k];
            }
            out[2*m]=quantize(re); out[2*m+1]=quantize(im);
        }
        return;
    }
#endif
#if defined(__ARM_NEON) && defined(LEO_DECIMATOR_COMPACT)
    if (!floating && factor==2 && !(length%16)) {
        if (f->kernel==15) { compact_15(f,x,count,out); return; }
        if (f->kernel==47) { compact_47(f,x,count,out); return; }
    }
#endif
#if defined(__ARM_NEON) && defined(LEO_DECIMATOR_FP32)
    float scratch[2*(TILE+4*(MAX_TAPS+16))],*phase[4];
    unsigned history=(f->count+factor-2)/factor;
    for (unsigned residue=0;residue<factor;++residue) {
        phase[residue]=scratch+2*(residue*(length+history+16)+history);
        ptrdiff_t k=-(ptrdiff_t)history;
        for (;k+4<=(ptrdiff_t)length;k+=4) {
            const int32_t *p=(const int32_t *)(x+2*(k*(ptrdiff_t)factor+(ptrdiff_t)residue));
            int16x8_t v=factor==2 ? vreinterpretq_s16_s32(vld2q_s32(p).val[0]) :
                vreinterpretq_s16_s32(vld4q_s32(p).val[0]);
            vst1q_f32(phase[residue]+2*k,vcvtq_f32_s32(vmovl_s16(vget_low_s16(v))));
            vst1q_f32(phase[residue]+2*k+4,vcvtq_f32_s32(vmovl_s16(vget_high_s16(v))));
        }
        for (;k<(ptrdiff_t)length;++k) {
            ptrdiff_t index=k*(ptrdiff_t)factor+(ptrdiff_t)residue;
            phase[residue][2*k]=x[2*index];
            phase[residue][2*k+1]=x[2*index+1];
        }
    }
    for (;m+16<=length;m+=16) {
        float32x4_t a=vdupq_n_f32(0),b=a,c=a,d=a,e=a,g=a,j=a,l=a;
        for (unsigned k=0;k<f->used;++k) {
            unsigned offset=f->offset[k], residue=(factor-offset%factor)%factor;
            const float *p=phase[residue]+2*((ptrdiff_t)m-(ptrdiff_t)((offset+factor-1)/factor));
            /* Scalar VFP coefficient conversion inside this NEON loop stalls
             * Cortex-A9's shared register file. Convert once at construction. */
            float32x4_t h=vld1q_dup_f32(f->fp+k);
            a=vmlaq_f32(a,vld1q_f32(p),h); b=vmlaq_f32(b,vld1q_f32(p+4),h);
            c=vmlaq_f32(c,vld1q_f32(p+8),h); d=vmlaq_f32(d,vld1q_f32(p+12),h);
            e=vmlaq_f32(e,vld1q_f32(p+16),h); g=vmlaq_f32(g,vld1q_f32(p+20),h);
            j=vmlaq_f32(j,vld1q_f32(p+24),h); l=vmlaq_f32(l,vld1q_f32(p+28),h);
        }
#define ROUND_STORE(A,B,OFFSET) do { \
        float32x4_t half=vdupq_n_f32(.5f); \
        A=vaddq_f32(A,half); B=vaddq_f32(B,half); \
        int32x4_t ia=vcvtq_s32_f32(A),ib=vcvtq_s32_f32(B); \
        ia=vaddq_s32(ia,vreinterpretq_s32_u32(vcltq_f32(A,vcvtq_f32_s32(ia)))); \
        ib=vaddq_s32(ib,vreinterpretq_s32_u32(vcltq_f32(B,vcvtq_f32_s32(ib)))); \
        vst1q_s16(out+2*m+OFFSET,vcombine_s16(vqmovn_s32(ia),vqmovn_s32(ib))); \
    } while (0)
        ROUND_STORE(a,b,0); ROUND_STORE(c,d,8); ROUND_STORE(e,g,16); ROUND_STORE(j,l,24);
#undef ROUND_STORE
    }
#else
#if defined(__ARM_NEON)
#if defined(LEO_DECIMATOR_PHASED)
    int16_t scratch[2*(TILE+4*(MAX_TAPS+16))],*phase[4];
    unsigned history=(f->count+factor-2)/factor;
    for (unsigned residue=0;residue<factor;++residue) {
        phase[residue]=scratch+2*(residue*(length+history+16)+history);
        ptrdiff_t k=-(ptrdiff_t)history;
        for (;k+4<=(ptrdiff_t)length;k+=4) {
            const int32_t *p=(const int32_t *)(x+2*(k*(ptrdiff_t)factor+(ptrdiff_t)residue));
            int16x8_t v=factor==2 ? vreinterpretq_s16_s32(vld2q_s32(p).val[0]) :
                vreinterpretq_s16_s32(vld4q_s32(p).val[0]);
            vst1q_s16(phase[residue]+2*k,v);
        }
        for (;k<(ptrdiff_t)length;++k) {
            ptrdiff_t index=k*(ptrdiff_t)factor+(ptrdiff_t)residue;
            phase[residue][2*k]=x[2*index]; phase[residue][2*k+1]=x[2*index+1];
        }
    }
#endif
    /* Each lane is a distinct output component. Packed IQ loads avoid per-tap
     * conversions and horizontal sums. Allocated zero halos make vector reads
     * safe at both ends; no output depends on a future input sample. */
    for (;m+16<=length;m+=16) {
        int32x4_t a=vdupq_n_s32(0),b=a,c=a,d=a,e=a,g=a,j=a,l=a;
        for (unsigned k=0;k<f->used;++k) {
#if defined(LEO_DECIMATOR_PHASED)
            unsigned offset=f->offset[k],residue=(factor-offset%factor)%factor;
            const int16_t *p=phase[residue]+2*((ptrdiff_t)m-(ptrdiff_t)((offset+factor-1)/factor));
#define LOAD_OUTPUTS(OFFSET) vld1q_s16(p+2*OFFSET)
#else
            const int32_t *p=(const int32_t *)(x+2*((ptrdiff_t)(m*factor)-(ptrdiff_t)f->offset[k]));
#define LOAD_OUTPUTS(OFFSET) (factor==2 ? vreinterpretq_s16_s32(vld2q_s32(p+OFFSET*factor).val[0]) : \
                vreinterpretq_s16_s32(vld4q_s32(p+OFFSET*factor).val[0]))
#endif
            int16x4_t h=vdup_n_s16(f->h[k]);
#define ACCUMULATE(LO,HI,OFFSET) do { \
            int16x8_t v=LOAD_OUTPUTS(OFFSET); \
            LO=vmlal_s16(LO,vget_low_s16(v),h); \
            HI=vmlal_s16(HI,vget_high_s16(v),h); \
        } while (0)
            ACCUMULATE(a,b,0); ACCUMULATE(c,d,4);
            ACCUMULATE(e,g,8); ACCUMULATE(j,l,12);
#undef ACCUMULATE
#undef LOAD_OUTPUTS
        }
        if (floating) {
#define STORE_FLOAT(A,OFFSET) vst1q_f32(floating+2*m+OFFSET,vmulq_n_f32(vcvtq_f32_s32(A),1.0f/16384))
            STORE_FLOAT(a,0); STORE_FLOAT(b,4); STORE_FLOAT(c,8); STORE_FLOAT(d,12);
            STORE_FLOAT(e,16); STORE_FLOAT(g,20); STORE_FLOAT(j,24); STORE_FLOAT(l,28);
#undef STORE_FLOAT
        } else {
            vst1q_s16(out+2*m,vcombine_s16(vqrshrn_n_s32(a,15),vqrshrn_n_s32(b,15)));
            vst1q_s16(out+2*m+8,vcombine_s16(vqrshrn_n_s32(c,15),vqrshrn_n_s32(d,15)));
            vst1q_s16(out+2*m+16,vcombine_s16(vqrshrn_n_s32(e,15),vqrshrn_n_s32(g,15)));
            vst1q_s16(out+2*m+24,vcombine_s16(vqrshrn_n_s32(j,15),vqrshrn_n_s32(l,15)));
        }
    }
#endif
#endif
    for (;m<length;++m) {
        int32_t re=0,im=0;
        for (unsigned k=0;k<f->used;++k) {
            ptrdiff_t p=2*((ptrdiff_t)(m*factor)-(ptrdiff_t)f->offset[k]);
            re+=(int32_t)x[p]*f->h[k]; im+=(int32_t)x[p+1]*f->h[k];
        }
        if (floating) {
            floating[2*m]=re*(1.0f/16384); floating[2*m+1]=im*(1.0f/16384);
        } else { out[2*m]=quantize(re); out[2*m+1]=quantize(im); }
    }
}

static void recursive_filter(leo_decimator *w, size_t count, int16_t *out)
{
#if defined(__ARM_NEON) && defined(LEO_DECIMATOR_RECURSIVE_PAIRS)
    /* Algebraic two-sample lookahead. Each section traverses the cache-sized
     * float tile in place. Keep quantization in a separate vector pass so its
     * scalar constants cannot force VFP/NEON synchronization in the recurrence.
     * This changes FP32 evaluation order; the independent reference remains
     * authoritative, including full-scale and near-threshold controls. */
    for (unsigned section=0;section<4;++section) {
        float a=w->denominator[2*section],b=w->denominator[2*section+1];
        float32x4_t prior1=vcombine_f32(vdup_n_f32(-a),vdup_n_f32(a*a-b));
        float32x4_t prior2=vcombine_f32(vdup_n_f32(-b),vdup_n_f32(a*b));
        float32x4_t feed=vcombine_f32(vdup_n_f32(0),vdup_n_f32(-a));
        float32x2_t y1=vld1_f32(w->state[section][0]);
        float32x2_t y2=vld1_f32(w->state[section][1]);
        size_t i=0;
        for (;i+2<=count;i+=2) {
            float32x4_t x=vld1q_f32(w->prefiltered+2*i);
            float32x4_t y=vmlaq_f32(x,vcombine_f32(vdup_n_f32(0),vget_low_f32(x)),feed);
            y=vmlaq_f32(y,vcombine_f32(y1,y1),prior1);
            y=vmlaq_f32(y,vcombine_f32(y2,y2),prior2);
            y1=vget_high_f32(y); y2=vget_low_f32(y);
            vst1q_f32(w->prefiltered+2*i,y);
        }
        if (i<count) {
            float32x2_t x=vld1_f32(w->prefiltered+2*i);
            x=vmls_n_f32(x,y1,a); x=vmls_n_f32(x,y2,b);
            y2=y1; y1=x; vst1_f32(w->prefiltered+2*i,x);
        }
        vst1_f32(w->state[section][0],y1); vst1_f32(w->state[section][1],y2);
    }
    size_t j=0;
    for (;j+4<=2*count;j+=4) {
        float32x4_t x=vld1q_f32(w->prefiltered+j);
        x=vminq_f32(vmaxq_f32(x,vdupq_n_f32(-32768)),vdupq_n_f32(32767));
        x=vaddq_f32(x,vdupq_n_f32(.5f));
        int32x4_t q=vcvtq_s32_f32(x);
        q=vaddq_s32(q,vreinterpretq_s32_u32(vcltq_f32(x,vcvtq_f32_s32(q))));
        vst1_s16(out+j,vqmovn_s32(q));
    }
    for (;j<2*count;++j) {
        float x=floorf(w->prefiltered[j]+.5f);
        out[j]=x>32767 ? 32767 : x< -32768 ? -32768 : (int16_t)x;
    }
#elif defined(__ARM_NEON)
    float32x2_t a=vld1_f32(w->state[0][0]),b=vld1_f32(w->state[0][1]);
    float32x2_t c=vld1_f32(w->state[1][0]),d=vld1_f32(w->state[1][1]);
    float32x2_t e=vld1_f32(w->state[2][0]),f=vld1_f32(w->state[2][1]);
    float32x2_t g=vld1_f32(w->state[3][0]),h=vld1_f32(w->state[3][1]);
    const float32x2_t c0=vld1_f32(w->denominator),c1=vld1_f32(w->denominator+2);
    const float32x2_t c2=vld1_f32(w->denominator+4),c3=vld1_f32(w->denominator+6);
    for (size_t i=0;i<count;++i) {
        float32x2_t x=vld1_f32(w->prefiltered+2*i);
#define SECTION(A,B,C) do { x=vmls_lane_f32(x,A,C,0); x=vmls_lane_f32(x,B,C,1); B=A; A=x; } while (0)
        SECTION(a,b,c0); SECTION(c,d,c1); SECTION(e,f,c2); SECTION(g,h,c3);
#undef SECTION
        x=vmin_f32(vmax_f32(x,vdup_n_f32(-32768)),vdup_n_f32(32767));
        x=vadd_f32(x,vdup_n_f32(.5f));
        int32x2_t q=vcvt_s32_f32(x);
        q=vadd_s32(q,vreinterpret_s32_u32(vclt_f32(x,vcvt_f32_s32(q))));
        int16x4_t narrow=vqmovn_s32(vcombine_s32(q,q));
        out[2*i]=vget_lane_s16(narrow,0); out[2*i+1]=vget_lane_s16(narrow,1);
    }
    vst1_f32(w->state[0][0],a); vst1_f32(w->state[0][1],b);
    vst1_f32(w->state[1][0],c); vst1_f32(w->state[1][1],d);
    vst1_f32(w->state[2][0],e); vst1_f32(w->state[2][1],f);
    vst1_f32(w->state[3][0],g); vst1_f32(w->state[3][1],h);
#else
    for (size_t i=0;i<count;++i) for (unsigned component=0;component<2;++component) {
        float x=w->prefiltered[2*i+component];
        for (unsigned k=0;k<4;++k) {
            x-=w->denominator[2*k]*w->state[k][0][component];
            x-=w->denominator[2*k+1]*w->state[k][1][component];
            w->state[k][1][component]=w->state[k][0][component]; w->state[k][0][component]=x;
        }
        x=floorf(x+.5f);
        out[2*i+component]=x>32767 ? 32767 : x< -32768 ? -32768 : (int16_t)x;
    }
#endif
}

int leo_decimator_run(leo_decimator *w, const int16_t *iq, size_t count, int16_t *out)
{
    if (!w || !iq || !out || count!=w->count) return -1;
#if defined(LEO_DECIMATOR_FFT)
    if (w->fast) return leo_decimator_fft_run(w->fast,iq,count,out);
#endif
    if (!w->a.count && w->factor!=4) {
        int16_t *source=w->source+2*MAX_TAPS;
        memset(w->source,0,2*MAX_TAPS*sizeof(int16_t));
        memcpy(source,iq,4*count);
        filter(&w->b,source,count,w->factor,out,NULL);
        return 0;
    }
    int16_t *source=w->source+2*MAX_TAPS, *middle=w->middle+2*MAX_TAPS;
    memset(w->source,0,2*MAX_TAPS*sizeof(int16_t));
    memset(w->middle,0,2*MAX_TAPS*sizeof(int16_t));
    memset(w->state,0,sizeof(w->state));
    /* Keep both filter stages in a cache-sized tile, carrying exact causal
     * history across tiles. Only a new dwell resets filter history. */
    for (size_t offset=0;offset<count;offset+=TILE) {
        size_t n=count-offset<TILE ? count-offset : TILE;
        memcpy(source,iq+2*offset,4*n);
        if (w->a.count) {
            filter(&w->a,source,n,2,middle,NULL);
            if (w->recursive) {
                filter(&w->b,middle,n/2,2,NULL,w->prefiltered);
                recursive_filter(w,n/4,out+offset/2);
            } else filter(&w->b,middle,n/2,2,out+offset/2,NULL);
        } else filter(&w->b,source,n,4,out+offset/2,NULL);
        if (offset+n<count) {
            memcpy(w->source,source+2*(n-MAX_TAPS),2*MAX_TAPS*sizeof(int16_t));
            if (w->a.count)
                memcpy(w->middle,middle+2*(n/2-MAX_TAPS),2*MAX_TAPS*sizeof(int16_t));
        }
    }
    return 0;
}
