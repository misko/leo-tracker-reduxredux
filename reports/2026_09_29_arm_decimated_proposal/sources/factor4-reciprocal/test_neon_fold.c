#define main proposal_probe_main
#include "proposal_probe.c"
#undef main
#include <assert.h>

static uint32_t state=0x91c7a53du;
static int16_t random_i16(void)
{
    state=1664525u*state+1013904223u;
    return (int16_t)(state>>16);
}

static void scalar_sanity(void)
{
    int16_t raw[4*16];
    for(size_t k=0;k<sizeof(raw)/sizeof(raw[0]);++k) raw[k]=random_i16();
    fftwf_complex got[7]={{0}},expected[7]={{0}}; int support[7]={0};
    fold_scalar(got,support,raw,1,2,7,1,3);
    for(size_t k=0;k<7;++k) {
        size_t a=4*(1+2+k)+2,q=a+12;
        float ar=(float)raw[q],ai=(float)raw[q+1];
        float br=(float)raw[a],bi=(float)raw[a+1];
        expected[k][0]=(ar*br)+(ai*bi);
        expected[k][1]=(ai*br)-(ar*bi);
        assert(support[k]==1);
    }
    assert(!memcmp(got,expected,sizeof(got)));
}

#ifdef LEO_PROPOSAL_NEON_FOLD
static void parity_rate(size_t rate)
{
    size_t n=(rate+375)/750,count=rate/50,start=rate/100;
    size_t samples=start+count+8;
    int16_t *raw=malloc(4*samples*sizeof(*raw));
    fftwf_complex *scalar=fftwf_alloc_complex(n),*neon=fftwf_alloc_complex(n);
    int *scalar_support=calloc(n,sizeof(*scalar_support));
    int *neon_support=calloc(n,sizeof(*neon_support));
    assert(raw&&scalar&&neon&&scalar_support&&neon_support);
    for(size_t k=0;k<4*samples;++k) raw[k]=random_i16();
    for(int rx=0;rx<2;++rx) for(int method=0;method<4;++method) {
        memset(scalar,0,n*sizeof(*scalar));memset(neon,0,n*sizeof(*neon));
        memset(scalar_support,0,n*sizeof(*scalar_support));
        memset(neon_support,0,n*sizeof(*neon_support));
        int lag=method<3?lags[method]:0;
        for(int frame=0;frame<FRAMES;++frame) {
            size_t off=(size_t)llround(frame*(double)rate/750.0);
            if(off>=count)break;
            size_t available=count-off,valid=available<n?available:n;
            if(lag)valid=available>(size_t)lag?fmin(valid,available-(size_t)lag):0;
            fold_scalar(scalar,scalar_support,raw,start,off,valid,rx,lag);
            fold_neon(neon,neon_support,raw,start,off,valid,rx,lag);
            assert(!memcmp(scalar,neon,n*sizeof(*scalar)));
            assert(!memcmp(scalar_support,neon_support,n*sizeof(*scalar_support)));
        }
    }
    free(neon_support);free(scalar_support);fftwf_free(neon);fftwf_free(scalar);free(raw);
}
#endif

int main(void)
{
    scalar_sanity();
#ifdef LEO_PROPOSAL_NEON_FOLD
    const size_t rates[]={2500000,5000000,7500000,10000000};
    for(int k=0;k<4;++k) parity_rate(rates[k]);
    puts("NEON fold passed: bit-exact per-frame parity, both receivers, lag 1/3/5 and power, all rates");
#else
    puts("scalar fold passed: direct-order sanity");
#endif
    return 0;
}
