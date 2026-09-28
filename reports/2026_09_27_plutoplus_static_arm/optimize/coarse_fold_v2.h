/* Exact register-resident CI16 fold. Existing scalar implementation remains
 * the portable oracle. Partial support is handled without padded input reads. */
static void opt_coarse_fold_ci16(leo_presence_workspace *w, const int16_t *iq,
    size_t count)
{
#if defined(__ARM_NEON) && !defined(LEO_PRESENCE_FORCE_PORTABLE)
    size_t starts[16], valid[16], paired[16], full=w->n;
    int frames=0;
    for (int f=0; f<16; ++f) {
        size_t start=(size_t)frame_start(w,0,f);
        if (start>=count) break;
        size_t available=count-start;
        starts[frames]=start;
        valid[frames]=available<w->n ? available : w->n;
        size_t p=available>LEO_PRESENCE_DIFFERENTIAL_LAG ?
            available-LEO_PRESENCE_DIFFERENTIAL_LAG : 0;
        paired[frames]=p<w->n ? p : w->n;
        if (paired[frames]<full) full=paired[frames];
        ++frames;
    }
    if (frames<2) { coarse_fold_ci16(w,iq,count);return; }
    size_t k=0;
    for (; k+3<full; k+=4) {
        int64x2_t r0=vdupq_n_s64(0),r1=r0,i0=r0,i1=r0,e0=r0,e1=r0;
        for (int f=0; f<frames; ++f) {
            int16x4x2_t a=vld2_s16(iq+2*(starts[f]+k));
            int16x4x2_t b=vld2_s16(iq+2*(starts[f]+k+LEO_PRESENCE_DIFFERENTIAL_LAG));
            int32x4_t x=vmull_s16(a.val[0],b.val[0]);
            int32x4_t y=vmull_s16(a.val[1],b.val[1]);
            r0=vaddq_s64(r0,vaddl_s32(vget_low_s32(x),vget_low_s32(y)));
            r1=vaddq_s64(r1,vaddl_s32(vget_high_s32(x),vget_high_s32(y)));
            x=vmull_s16(a.val[0],b.val[1]); y=vmull_s16(a.val[1],b.val[0]);
            i0=vaddq_s64(i0,vsubl_s32(vget_low_s32(x),vget_low_s32(y)));
            i1=vaddq_s64(i1,vsubl_s32(vget_high_s32(x),vget_high_s32(y)));
            x=vmull_s16(a.val[0],a.val[0]); y=vmull_s16(a.val[1],a.val[1]);
            e0=vaddq_s64(e0,vaddl_s32(vget_low_s32(x),vget_low_s32(y)));
            e1=vaddq_s64(e1,vaddl_s32(vget_high_s32(x),vget_high_s32(y)));
        }
        int64_t real[4],imag[4],energy[4];
        vst1q_s64(real,r0);vst1q_s64(real+2,r1);
        vst1q_s64(imag,i0);vst1q_s64(imag+2,i1);
        vst1q_s64(energy,e0);vst1q_s64(energy+2,e1);
        for (size_t j=0;j<4;++j) {
            w->power_native_folded[k+j]=opt_fold_double(energy[j]);
            w->diff_folded[k+j]=opt_fold_double(real[j])+I*opt_fold_double(imag[j]);
            w->support[k+j]=frames;w->diff_support[k+j]=frames;
        }
    }
    for (;k<w->n;++k) {
        int64_t energy=0,real=0,imag=0;int support=0,diff_support=0;
        for (int f=0;f<frames;++f) {
            if (k>=valid[f]) continue;
            size_t offset=2*(starts[f]+k);
            int64_t ar=iq[offset],ai=iq[offset+1];
            energy+=ar*ar+ai*ai;++support;
            if(k<paired[f]) {
                int64_t br=iq[offset+2*LEO_PRESENCE_DIFFERENTIAL_LAG];
                int64_t bi=iq[offset+2*LEO_PRESENCE_DIFFERENTIAL_LAG+1];
                real+=ar*br+ai*bi;imag+=ar*bi-ai*br;++diff_support;
            }
        }
        w->power_native_folded[k]=opt_fold_double(energy);
        w->diff_folded[k]=opt_fold_double(real)+I*opt_fold_double(imag);
        w->support[k]=support;w->diff_support[k]=diff_support;
    }
#else
    coarse_fold_ci16(w,iq,count);
#endif
}
