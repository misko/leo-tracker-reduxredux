#include "dwell_input.h"
#include <assert.h>
#include <stdio.h>

static void run_rate(size_t rate)
{
    size_t dwell=rate*120/1000,probe=rate/50,stride=rate/100;
    int16_t *iq=malloc(4*dwell*sizeof(*iq));assert(iq);
    for(size_t k=0;k<dwell;++k)for(int rx=0;rx<2;++rx){iq[4*k+2*rx]=(k&1)?INT16_MIN:INT16_MAX;iq[4*k+2*rx+1]=(k%3)?INT16_MAX:INT16_MIN;}
    leo_dwell_input d;assert(!leo_dwell_input_prepare(&d,iq,dwell));
    assert(2.0*dwell*1073741824.0<4503599627370496.0);
    for(int rx=0;rx<2;++rx){
        for(int window=0;window<11;++window){size_t begin=(size_t)window*stride,end=begin+probe;double local=0;for(size_t k=begin;k<end;++k){double re=(double)iq[4*k+2*rx]/32768.0,im=(double)iq[4*k+2*rx+1]/32768.0;local+=re*re+im*im;}assert(d.prefix[rx][end]-d.prefix[rx][begin]==local);assert(creal(d.raw[rx][begin])==(double)iq[4*begin+2*rx]);assert(cimag(d.raw[rx][end-1])==(double)iq[4*(end-1)+2*rx+1]);}
        size_t begin=dwell-probe+1,end=dwell;double tail=0;for(size_t k=begin;k<end;++k){double re=(double)iq[4*k+2*rx]/32768.0,im=(double)iq[4*k+2*rx+1]/32768.0;tail+=re*re+im*im;}assert(d.prefix[rx][end]-d.prefix[rx][begin]==tail);
    }
    leo_dwell_input_free(&d);free(iq);
}
int main(void){size_t rates[]={2500000,5000000,7500000,10000000};for(int i=0;i<4;++i)run_rate(rates[i]);puts("dwell input passed all rates, full-scale 120 ms, 22 overlapping windows, exact prefixes, and tails");}
