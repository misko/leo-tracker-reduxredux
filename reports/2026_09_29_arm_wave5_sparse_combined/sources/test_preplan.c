#define LEO_PROPOSAL_LIBRARY 1
#define LEO_PROPOSAL_OMIT_POWER 1
#include "proposal_core.c"
#include <assert.h>

static void legacy_fold(fftwf_complex *out,int *support,const int16_t *raw,
    size_t n,size_t count,double rate,size_t start,int rx,int lag)
{
    memset(out,0,n*sizeof(*out)); memset(support,0,n*sizeof(*support));
    for(int frame=0;frame<FRAMES;frame++) {
        size_t off=(size_t)llround(frame*rate/750.0);
        if(off>=count)break;
        size_t available=count-off,valid=available<n?available:n;
        if(lag)valid=available>(size_t)lag?
            (valid<available-(size_t)lag?valid:available-(size_t)lag):0;
        for(size_t k=0;k<valid;k++) {
            size_t a=4*(start+off+k)+2*(size_t)rx;
            float ar=(float)raw[a],ai=(float)raw[a+1];
            size_t q=a+4*(size_t)lag;
            float qr=(float)raw[q],qi=(float)raw[q+1];
            float rr=qr*ar,ri=qi*ai,ir=qi*ar,ii=qr*ai;
            out[k][0]+=rr+ri; out[k][1]+=ir-ii; ++support[k];
        }
    }
    for(size_t k=0;k<n;k++)if(support[k]) {
        out[k][0]/=support[k]; out[k][1]/=support[k];
    }
}

static void test_rate(size_t rate)
{
    size_t n=(rate+375)/750,z=next_power2(n),count=rate/50,dwell=rate*120/1000;
    fftwf_complex *t=fftwf_alloc_complex(n),*legacy=fftwf_alloc_complex(n);
    fftwf_complex *planned=fftwf_alloc_complex(n),*a=fftwf_alloc_complex(z),*b=fftwf_alloc_complex(z);
    int16_t *raw=malloc(dwell*4*sizeof(*raw)); int *support=calloc(n,sizeof(*support));
    assert(t&&legacy&&planned&&a&&b&&raw&&support); memset(t,0,n*sizeof(*t));
    for(size_t k=0;k<dwell*4;k++)raw[k]=(int16_t)((k*40503u+32768u)&65535u);
    bank plan; assert(!bank_init(&plan,t,n,(double)rate));
    for(size_t k=0;k<z;k++) {
        size_t scaled=k*n;
        assert(plan.resample_source[k]==scaled/z);
        assert(plan.resample_fraction[k]==(float)(scaled%z)/(float)z);
    }
    for(int rx=0;rx<2;rx++)for(int m=0;m<LAG_COUNT;m++) {
        legacy_fold(legacy,support,raw,n,count,(double)rate,0,rx,lags[m]);
        memset(planned,0,n*sizeof(*planned));
        for(int frame=0;frame<FRAMES;frame++)fold_scalar(planned,raw,0,
            plan.frame_offset[frame],plan.valid[m][frame],rx,lags[m]);
        for(size_t k=0;k<n;k++) {
            assert(support[k]==plan.support[m][k]);
            if(plan.support[m][k]) {
                planned[k][0]/=plan.support[m][k]; planned[k][1]/=plan.support[m][k];
            }
        }
        assert(!memcmp(legacy,planned,n*sizeof(*legacy)));
        resample_periodic(&plan,legacy,a); resample_periodic(&plan,planned,b);
        assert(!memcmp(a,b,z*sizeof(*a)));
    }
    bank_free(&plan); free(support); free(raw); fftwf_free(b); fftwf_free(a);
    fftwf_free(planned); fftwf_free(legacy); fftwf_free(t);
}

int main(void)
{
    const size_t rates[]={2500000,5000000,7500000,10000000};
    for(int k=0;k<4;k++)test_rate(rates[k]);
    puts("proposal preplan bitwise parity: resample geometry, support, full-range CI16 fold, all rates");
    return 0;
}
