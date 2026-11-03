static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t rng=0xa9c1742du;
static int16_t random_i16(void){rng=1664525u*rng+1013904223u;return (int16_t)(rng>>16);}
static double random_template(void){rng=1664525u*rng+1013904223u;return ((rng>>8)*0x1p-23-1)*4.0;}

static void check_rate(uint32_t rate,size_t stride)
{
    size_t n=(size_t)ceil(rate*4.4e-6);int16_t *samples=calloc(stride*n,sizeof(*samples));
    int16_t *q=calloc(2*n,sizeof(*q));double complex *t=calloc(n,sizeof(*t));assert(samples&&q&&t);
    double scale=256.0;
    for(size_t k=0;k<n;k++){samples[stride*k]=random_i16();samples[stride*k+1]=random_i16();
        t[k]=random_template()+I*random_template();q[2*k]=glrt_quantize_q15(creal(t[k]),scale);q[2*k+1]=glrt_quantize_q15(cimag(t[k]),scale);}
    double complex got=glrt_ci16_q15_dot(samples,stride,q,n,1.0/scale),reference=0;
    for(size_t k=0;k<n;k++)reference+=(samples[stride*k]+I*samples[stride*k+1])*t[k];
    double bound=sqrt(2.0)*32768.0*n*(1u<<(n<=11?0:n<=22?1:2))/scale+1e-6;assert(cabs(got-reference)<=bound);
    for(size_t k=0;k<n;k++){samples[stride*k]=-32768;samples[stride*k+1]=-32768;q[2*k]=-32768;q[2*k+1]=32767;}
    for(size_t k=0;k<n;k++){q[2*k]=-2047;q[2*k+1]=2047;}
    got=glrt_ci16_q15_dot(samples,stride,q,n,1.0);assert(isfinite(creal(got))&&isfinite(cimag(got))&&fabs(creal(got))<=2147483647.0*4);
    free(t);free(q);free(samples);
}

static void check_glrt_error(uint32_t rate)
{
    size_t n=(rate+375)/750,count=rate/50;leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));int16_t *iq=calloc(2*count,sizeof(*iq));assert(exact&&control&&samples&&iq);
    for(size_t k=0;k<n;k++){exact[k]=(leo_presence_complex){random_template(),random_template()};control[k]=(leo_presence_complex){random_template(),random_template()};}
    for(size_t k=0;k<count;k++){iq[2*k]=random_i16();iq[2*k+1]=random_i16();samples[k]=(leo_presence_complex){iq[2*k],iq[2*k+1]};}
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);assert(w&&!ingest(w,samples,count));double reference[3],candidate[3];
    assert(!glrt(w,count,0,123000.0,0,16,1,reference));leo_q15_glrt_ci16=iq;leo_q15_glrt_stride=2;
    w->have_rotations=0;assert(!glrt(w,count,0,123000.0,0,16,1,candidate));leo_q15_glrt_ci16=NULL;leo_q15_glrt_stride=0;
    for(int k=0;k<2;k++)assert(fabs(candidate[k]-reference[k])<=5e-4*fmax(1.0,fabs(reference[k])));
    assert(candidate[2]==reference[2]);leo_presence_destroy(w);free(iq);free(samples);free(control);free(exact);
}

int main(void)
{
    leo_full_search_result dummy;assert(leo_full_search_run_prepared_ci16(NULL,NULL,NULL,NULL,NULL,4,0,&dummy)==-1);
    assert(leo_q15_glrt_ci16==NULL&&leo_q15_glrt_stride==0);
    assert(glrt_quantize_q15(100,1000)==32767);assert(glrt_quantize_q15(-100,1000)==-32768);
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int k=0;k<4;k++){check_rate(rates[k],2);check_rate(rates[k],4);check_glrt_error(rates[k]);}
    puts("adaptive-Q int32 GLRT dot passed: bounds, residual parity, extrema, strides 2/4, all rates");
    return 0;
}
