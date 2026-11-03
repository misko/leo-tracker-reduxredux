#include "kernel/private/dwell_input.h"
#include <assert.h>
#include <string.h>

static void compare(const leo_dwell_input *d,const int16_t *iq,size_t n,int receivers) {
    for(int rx=0;rx<receivers;++rx) {
        double prefix=0;
        assert(d->prefix[rx][0]==0);
        for(size_t k=0;k<n;++k) {
            double real=iq[2*receivers*k+2*rx],imag=iq[2*receivers*k+2*rx+1];
            double complex raw=real+I*imag;
            assert(!memcmp(&raw,&d->raw[rx][k],sizeof(raw)));
            real/=32768.0;imag/=32768.0;
            assert(d->normalized[rx][2*k]==(float)real);
            assert(d->normalized[rx][2*k+1]==(float)imag);
            prefix=prefix+real*real+imag*imag;
            assert(!memcmp(&prefix,&d->prefix[rx][k+1],sizeof(prefix)));
        }
    }
}

int main(void) {
    const size_t n=65536;
    int16_t *iq=malloc(4*n*sizeof(*iq));assert(iq);
    for(size_t k=0;k<n;++k) {
        iq[4*k]=(int16_t)((int)k-32768);
        iq[4*k+1]=(int16_t)(32767-(int)k);
        iq[4*k+2]=(int16_t)((int)((k*173u)%65536)-32768);
        iq[4*k+3]=INT16_MIN;
    }
    leo_dwell_input d={0};
    assert(!leo_dwell_input_prepare(&d,iq,n));compare(&d,iq,n,2);
    double complex *original=d.raw[0];
    assert(!leo_dwell_input_prepare_reuse(&d,iq,n/2));
    assert(d.raw[0]==original);compare(&d,iq,n/2,2);
    leo_dwell_input_free(&d);
    assert(!leo_dwell_input_prepare_single(&d,iq,n));compare(&d,iq,n,1);
    assert(!leo_dwell_input_prepare_reuse(&d,iq,n));compare(&d,iq,n,2);
    for(size_t k=0;k<4*n;++k)iq[k]=INT16_MIN;
    assert(!leo_dwell_input_prepare_reuse(&d,iq,n));compare(&d,iq,n,2);
    assert(d.prefix[0][n]==2.0*n);
    for(size_t k=0;k<4*n;++k)iq[k]=0;
    assert(!leo_dwell_input_prepare_single_reuse(&d,iq,n));compare(&d,iq,n,1);
    leo_dwell_input_free(&d);free(iq);
    return 0;
}
