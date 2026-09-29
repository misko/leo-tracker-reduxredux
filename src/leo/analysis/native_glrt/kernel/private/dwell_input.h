#ifndef LEO_WAVE6_DWELL_INPUT_H
#define LEO_WAVE6_DWELL_INPUT_H
#include <complex.h>
#include <stdint.h>
#include <stdlib.h>

typedef struct {
    size_t count,capacity;
    double complex *raw[2];
    float *normalized[2];
    double *prefix[2];
} leo_dwell_input;

static void leo_dwell_input_free(leo_dwell_input *d)
{
    if(!d)return;
    for(int rx=0;rx<2;++rx){free(d->raw[rx]);free(d->normalized[rx]);free(d->prefix[rx]);}
    *d=(leo_dwell_input){0};
}

static int leo_dwell_input_reserve(leo_dwell_input *d,size_t count)
{
    if(!d||!count||count>(SIZE_MAX/sizeof(double complex))||
       count>SIZE_MAX/(2*sizeof(float))||count==SIZE_MAX)return -1;
    if(d->capacity>=count)return 0;
    leo_dwell_input replacement={.capacity=count};
    for(int rx=0;rx<2;++rx) {
        replacement.raw[rx]=malloc(count*sizeof(*replacement.raw[rx]));
        replacement.normalized[rx]=malloc(2*count*sizeof(*replacement.normalized[rx]));
        replacement.prefix[rx]=malloc((count+1)*sizeof(*replacement.prefix[rx]));
        if(!replacement.raw[rx]||!replacement.normalized[rx]||!replacement.prefix[rx]){
            leo_dwell_input_free(&replacement);return -1;
        }
    }
    leo_dwell_input_free(d);*d=replacement;return 0;
}

static int leo_dwell_input_prepare_reuse(leo_dwell_input *d,const int16_t *ci16,
    size_t count)
{
    if(!ci16||leo_dwell_input_reserve(d,count))return -1;
    d->count=count;
    for(int rx=0;rx<2;++rx) {
        d->prefix[rx][0]=0;
        for(size_t k=0;k<count;++k) {
            int16_t ir=ci16[4*k+2*rx],ii=ci16[4*k+2*rx+1];
            double real=(double)ir,imag=(double)ii;
            d->raw[rx][k]=real+I*imag;
            real/=32768.0;imag/=32768.0;
            d->normalized[rx][2*k]=(float)real;
            d->normalized[rx][2*k+1]=(float)imag;
            d->prefix[rx][k+1]=d->prefix[rx][k]+real*real+imag*imag;
        }
    }
    return 0;
}

static int leo_dwell_input_prepare(leo_dwell_input *d,const int16_t *ci16,size_t count)
{
    if(!d)return -1;
    *d=(leo_dwell_input){0};
    if(leo_dwell_input_prepare_reuse(d,ci16,count)){
        leo_dwell_input_free(d);return -1;
    }
    return 0;
}
#endif
