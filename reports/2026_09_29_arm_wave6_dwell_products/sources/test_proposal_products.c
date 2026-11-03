#include "proposal_core.c"
#include <assert.h>

static void test_rate(size_t rate){
    size_t n=(rate+375)/750,dwell=rate*120/1000,stride=rate/100;
    fftwf_complex *t=fftwf_alloc_complex(n),*a=fftwf_alloc_complex(n),*b=fftwf_alloc_complex(n);
    int16_t *raw=malloc(4*dwell*sizeof(*raw));assert(t&&a&&b&&raw);
    for(size_t k=0;k<n;k++){t[k][0]=(float)((int)(k%17)-8);t[k][1]=(float)((int)(k%13)-6);}
    for(size_t k=0;k<dwell;k++)for(int q=0;q<4;q++)raw[4*k+q]=(int16_t)((k*7919u+q*17011u)&65535u);
    raw[0]=INT16_MIN;raw[1]=INT16_MAX;raw[4*dwell-2]=INT16_MAX;raw[4*dwell-1]=INT16_MIN;
    bank bank;assert(!bank_init(&bank,t,n,(double)rate));leo_proposal_dwell_products p;
    assert(!leo_proposal_products_prepare(&p,raw,dwell));assert(p.count==dwell);
    for(int window=0;window<11;window++)for(int rx=0;rx<2;rx++)for(int m=0;m<3;m++){
        memset(a,0,n*sizeof(*a));memset(b,0,n*sizeof(*b));
        for(int frame=0;frame<FRAMES;frame++){
            fold_scalar(a,raw,(size_t)window*stride,bank.frame_offset[frame],bank.valid[m][frame],rx,lags[m]);
            fold_cached(b,p.lag[rx][m],(size_t)window*stride+bank.frame_offset[frame],bank.valid[m][frame]);
        }
        assert(!memcmp(a,b,n*sizeof(*a)));
    }
    assert(leo_proposal_products_prepare(NULL,raw,dwell)==-1);
    leo_proposal_products_free(&p);bank_free(&bank);free(raw);fftwf_free(b);fftwf_free(a);fftwf_free(t);
}
int main(void){size_t rates[]={2500000,5000000,7500000,10000000};for(int k=0;k<4;k++)test_rate(rates[k]);puts("dwell lag products passed all rates, receivers, lags, 22 windows, frame boundaries, extremes, and exact fold order");}
