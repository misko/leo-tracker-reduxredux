#include <assert.h>
#include <complex.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "ordinary_glrt_fine.h"

static void test_band(void)
{
    for (size_t size=5000;size<=20000;size+=5000) {
        size_t radius=leo_fine_band_radius(size,500.0);
        assert(radius==800);
        float complex *full=malloc(size*sizeof(*full));
        float complex *band=malloc((2*radius+1)*sizeof(*band));
        assert(full && band);
        for (size_t k=0;k<size;++k) full[k]=(float)k+I*(float)(size-k);
        leo_fine_band_copy(band,full,size,radius);
        const ptrdiff_t extent=(ptrdiff_t)radius;
        /* Exercise each legal coarse center, including clipped end windows. */
        for (ptrdiff_t center=-extent;center<=extent;center+=160) {
            ptrdiff_t begin=center-160>-extent ? center-160 : -extent;
            ptrdiff_t end=center+160<extent ? center+160 : extent;
            size_t cell=leo_fine_band_index((begin+(ptrdiff_t)size)%size,size,radius);
            for (ptrdiff_t bin=begin;bin<=end;++bin)
                assert(band[cell++]==full[(bin+(ptrdiff_t)size)%size]);
        }
        free(full);
        free(band);
    }
}

static void test_energy(void)
{
    const int count=3600000;
    double *prefix=malloc((count+1)*sizeof(*prefix));
    assert(prefix);
    prefix[0]=0;
    int64_t raw_total=0;
    for (int k=0;k<count;++k) {
        int32_t re=INT16_MIN+(k%4 ? 0 : k%65536), im=INT16_MIN;
        double real=re*0x1p-15, imag=im*0x1p-15;
        prefix[k+1]=prefix[k]+real*real+imag*imag;
        raw_total+=(int64_t)re*re+(int64_t)im*im;
    }
    assert(leo_fine_span_energy(prefix,0,count)==(double)raw_total);
    for (int start=0;start<count-10000;start+=2123) {
        double expected=0, candidate=0;
        for (int begin=start;begin<start+10000;begin+=88) {
            for (int k=begin;k<begin+44;++k) {
                double re=INT16_MIN+(k%4 ? 0 : k%65536), im=INT16_MIN;
                expected+=re*re+im*im;
            }
            candidate+=leo_fine_span_energy(prefix,begin,begin+44);
        }
        assert(candidate==expected);
    }
    free(prefix);
}

int main(void)
{
    test_band();
    test_energy();
    return 0;
}
