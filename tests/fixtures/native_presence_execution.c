/* Test-only access to private execution helpers; no installed API changes. */
#include "../../src/leo/analysis/native_presence/presence.c"

double test_magnitude(double real, double imag)
{ return magnitude(CMPLX(real,imag)); }

size_t test_execution_bytes(uint32_t rate)
{
    size_t n=(size_t)nearbyint(rate/750.0);
    return sizeof(leo_presence_workspace)+CONDITIONED_TABLES*n*sizeof(double complex)
#if LEO_PRESENCE_PRECOMPUTE
        +n*sizeof(double complex)
#endif
        ;
}

int test_conditioned_scores(leo_presence_workspace *w, const leo_presence_complex *samples,
    size_t count, int epoch, double center, double *scores)
{
    if (ingest(w,samples,count)) return -1;
    double frequencies[42];
    int nf=grid(fmax(-400000,center-LEO_PRESENCE_CONDITIONED_RADIUS),
        fmin(400000,center+LEO_PRESENCE_CONDITIONED_RADIUS),100,frequencies);
    if (nf<1 || nf>CONDITIONED_TABLES) return -1;
    conditioned_scores(w,count,epoch,frequencies,nf,scores);
    return nf;
}

int test_rounding_guards(leo_presence_workspace *w, const leo_presence_complex *samples,
    const int16_t *iq, size_t count)
{
    int original=fegetround(), modes[]={FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO}, failures=0;
    for (size_t k=0; k<sizeof(modes)/sizeof(*modes); ++k) {
        if (fesetround(modes[k])) { failures|=1; break; }
        leo_presence_result result;
        double scores[3];
        if (leo_presence_run(w,samples,count,&result)!=-1 ||
            leo_presence_run_ci16(w,iq,count,&result)!=-1 ||
            leo_presence_coarse(w,samples,count,w->grid)!=-1 ||
            leo_presence_coarse_ci16(w,iq,count,w->grid)!=-1 ||
            leo_presence_glrt(w,samples,count,317,173123,.375,scores)!=-1 ||
            leo_presence_confirm_ci16(w,iq,count,317,&result)!=-1) failures|=2;
    }
    if (fesetround(original)) failures|=4;
    return failures;
}
