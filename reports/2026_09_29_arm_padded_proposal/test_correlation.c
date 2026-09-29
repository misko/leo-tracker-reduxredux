#define main proposal_main
#include "proposal_probe.c"
#undef main
#include <assert.h>

int main(void) {
    const int rates[]={2500000,5000000,7500000,10000000};
    for(int r=0;r<4;r++) {
        size_t n=(size_t)llround(rates[r]/750.0);
        fftwf_complex *t=fftwf_alloc_complex(n);
        for(size_t k=0;k<n;k++){t[k][0]=sin(k*0.113)+cos(k*0.713);t[k][1]=cos(k*0.317);}
        bank b; assert(!bank_init(&b,t,n,rates[r]));
        fftwf_complex *ref=fftwf_alloc_complex(n),*x=fftwf_alloc_complex(n);
        float *score=malloc(n*sizeof(*score));
        for(int m=0;m<4;m++) {
            for(size_t k=0;k<n;k++) {
                size_t q=(k+(m<3?lags[m]:0))%n;
                ref[k][0]=m<3?t[q][0]*t[k][0]+t[q][1]*t[k][1]:power(t[k][0],t[k][1]);
                ref[k][1]=m<3?t[q][1]*t[k][0]-t[q][0]*t[k][1]:0;
                x[k][0]=sin(k*0.323)+cos(k*0.047);x[k][1]=m<3?cos(k*0.227):0;
            }
            float rn,xn; center_norm(ref,n,&rn);center_norm(x,n,&xn);
            memcpy(b.time,x,n*sizeof(*x));
            for(size_t k=n;k<b.fft_n;k++){b.time[k][0]=123;b.time[k][1]=-456;}
            correlate(&b,score,m);
            const size_t points[]={0,1,2,n/7,n/2,n-2,n-1};
            for(size_t p=0;p<sizeof(points)/sizeof(points[0]);p++) {
                size_t lag=points[p];double re=0,im=0;
                for(size_t j=0;j<n;j++){size_t k=(j+lag)%n;re+=(double)x[k][0]*ref[j][0]+(double)x[k][1]*ref[j][1];im+=(double)x[k][1]*ref[j][0]-(double)x[k][0]*ref[j][1];}
                double expected=(m<3?hypot(re,im):re)/((double)xn*rn);
                assert(fabs(score[lag]-expected)<2e-5);
            }
        }
        memset(b.time,0,n*sizeof(*b.time));correlate(&b,score,0);
        for(size_t k=0;k<n;k++)assert(score[k]==0);
        free(score);fftwf_free(ref);fftwf_free(x);bank_free(&b);fftwf_free(t);
    }
    puts("all-rate padded correlation matches direct circular sums");return 0;
}
