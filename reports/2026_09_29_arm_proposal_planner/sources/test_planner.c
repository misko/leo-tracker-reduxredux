#define main proposal_probe_main
#include "proposal_probe.c"
#undef main
#include <assert.h>

int main(void)
{
    enum { N=60 };
    fftwf_complex *reference=fftwf_alloc_complex(N);
    assert(reference);
    for(int k=0;k<N;++k) {
        reference[k][0]=(float)((k*17)%31-15);
        reference[k][1]=(float)((k*11)%29-14);
    }
    bank b;
    assert(!bank_init(&b,reference,N,2500000.0));
    assert(b.forward&&b.backward&&b.planning_wall_ms>=0.0);
    for(int method=0;method<4;++method)
        assert(isfinite(b.reference_norm[method])&&b.reference_norm[method]>0.0f);
    for(int k=0;k<N;++k) {
        b.time[k][0]=reference[k][0];
        b.time[k][1]=reference[k][1];
    }
    correlate(&b,b.scores[0],0);
    for(int k=0;k<N;++k) assert(isfinite(b.scores[0][k]));
    printf("planner passed: %s, planning_wall_ms=%.9g, setup excluded from window timer\n",
        LEO_PROPOSAL_PLAN_FLAG==FFTW_MEASURE?"measure":"estimate",b.planning_wall_ms);
    bank_free(&b);fftwf_free(reference);return 0;
}
