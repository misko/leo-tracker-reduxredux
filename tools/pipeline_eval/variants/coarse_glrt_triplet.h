/* Three consecutive native epochs share template and sliding sample loads. */
#ifndef LEO_COARSE_GLRT_TRIPLET_H
#define LEO_COARSE_GLRT_TRIPLET_H

#if defined(__ARM_NEON)
typedef float32x4_t leo_triplet_vector;
#define LEO_TRIPLET_ADD(a,b) vaddq_f32((a),(b))
#define LEO_TRIPLET_SUB(a,b) vsubq_f32((a),(b))
#define LEO_TRIPLET_MUL(a,b) vmulq_f32((a),(b))
#define LEO_TRIPLET_SPLAT(a) vdupq_n_f32(a)
#define LEO_TRIPLET_LOAD(a) vld1q_f32(a)
#else
typedef float leo_triplet_vector __attribute__((vector_size(16)));
#define LEO_TRIPLET_ADD(a,b) ((a)+(b))
#define LEO_TRIPLET_SUB(a,b) ((a)-(b))
#define LEO_TRIPLET_MUL(a,b) ((a)*(b))
#define LEO_TRIPLET_SPLAT(a) ((leo_triplet_vector){a,a,a,a})
static inline leo_triplet_vector leo_triplet_load(const float *at)
{
    leo_triplet_vector out;
    memcpy(&out,at,sizeof(out));
    return out;
}
#define LEO_TRIPLET_LOAD(a) leo_triplet_load(a)
#endif

static inline void leo_triplet_finish(leo_triplet_vector r, leo_triplet_vector i,
    float inverse, float *sum)
{
#if defined(__ARM_NEON)
    vst1q_f32(sum,vaddq_f32(vld1q_f32(sum),vmulq_n_f32(coarse_magnitude(r,i),inverse)));
#else
    for (int f=0;f<4;++f) sum[f]+=sqrtf(r[f]*r[f]+i[f]*i[f])*inverse;
#endif
}

static inline void leo_coarse_triplet(const float *samples, const float *real,
    const float *imag, int taps, const float inv[3], float *sum)
{
    for (int f=0;f<12;f+=4) {
        leo_triplet_vector r0=LEO_TRIPLET_SPLAT(0.0f),r1=r0,r2=r0,i0=r0,i1=r0,i2=r0;
        float xr0=samples[0],xi0=samples[1],xr1=samples[2],xi1=samples[3];
        for (int k=0;k<taps;++k) {
            float xr2=samples[2*k+4],xi2=samples[2*k+5];
            leo_triplet_vector rr=LEO_TRIPLET_LOAD(real+12*k+f);
            leo_triplet_vector ri=LEO_TRIPLET_LOAD(imag+12*k+f);
#define LEO_TRIPLET_ACCUMULATE(j) do { \
    leo_triplet_vector xr=LEO_TRIPLET_SPLAT(xr##j),xi=LEO_TRIPLET_SPLAT(xi##j); \
    r##j=LEO_TRIPLET_ADD(r##j,LEO_TRIPLET_ADD(LEO_TRIPLET_MUL(xr,rr),LEO_TRIPLET_MUL(xi,ri))); \
    i##j=LEO_TRIPLET_ADD(i##j,LEO_TRIPLET_SUB(LEO_TRIPLET_MUL(xi,rr),LEO_TRIPLET_MUL(xr,ri))); \
} while (0)
            LEO_TRIPLET_ACCUMULATE(0);
            LEO_TRIPLET_ACCUMULATE(1);
            LEO_TRIPLET_ACCUMULATE(2);
#undef LEO_TRIPLET_ACCUMULATE
            xr0=xr1;xi0=xi1;xr1=xr2;xi1=xi2;
        }
        leo_triplet_finish(r0,i0,inv[0],sum+f);
        leo_triplet_finish(r1,i1,inv[1],sum+12+f);
        leo_triplet_finish(r2,i2,inv[2],sum+24+f);
    }
}

#undef LEO_TRIPLET_ADD
#undef LEO_TRIPLET_SUB
#undef LEO_TRIPLET_MUL
#undef LEO_TRIPLET_SPLAT
#undef LEO_TRIPLET_LOAD
#endif
