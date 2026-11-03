static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t state=0x51f20a7du;
static double random_value(void){state=1664525u*state+1013904223u;return ((state>>8)*0x1p-23-1)*.25;}

static float complex weighted_value(leo_presence_workspace *w,int start,int k)
{
    double complex a=w->samples[start+k],b=conj(w->exact[k]);
    return (float)(creal(a)*creal(b)-cimag(a)*cimag(b))+
        I*(float)(creal(a)*cimag(b)+cimag(a)*creal(b));
}

static void check_rate(uint32_t rate,int partial)
{
    size_t n=(rate+375)/750,count=partial?(size_t)ceil(rate/375.0):rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));assert(exact&&control&&samples);
    for(size_t k=0;k<n;k++){exact[k]=(leo_presence_complex){random_value(),random_value()};control[k]=(leo_presence_complex){random_value(),random_value()};}
    for(size_t k=0;k<count;k++)samples[k]=(leo_presence_complex){random_value(),random_value()};
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);assert(w&&!ingest(w,samples,count));
    assert(w->fine_fft.size==rate/1000&&w->fine_step_hz==1000.0);
    w->acquisition_first_frame=0;leo_fine_precision_cache cache;
    assert(!leo_fine_precision_init(&cache,w->fine_fft.size));double scores[9];
    assert(!leo_fine_precision_scores(w,count,0,-4000,9,scores,&cache));assert(cache.entries[0].frames>0);
    const int bins[]={0,1,7,-1,-9};size_t last=(size_t)symbol_start(w,301)-1;
    (void)last;
    for(int frame_slot=0;frame_slot<cache.entries[0].frames;frame_slot++){
        int frame=cache.entries[0].frame_indices[frame_slot];
        int start=frame_start(w,0,frame+w->acquisition_first_frame);
        for(size_t q=0;q<sizeof(bins)/sizeof(bins[0]);q++){
            int bin=bins[q],wrapped=(bin%(int)cache.size+(int)cache.size)%(int)cache.size;
            double complex direct=0;
            for(int symbol=2;symbol<302;symbol+=2){int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
                for(int k=begin;k<end;k++){double phase=-6.2831853071795864769*(double)bin*k/cache.size;direct+=(double complex)weighted_value(w,start,k)*(cos(phase)+I*sin(phase));}}
            float complex got=cache.entries[0].spectra[frame_slot][wrapped];
            double error=cabs((double complex)got-direct),scale=fmax(1.0,cabs(direct));
            assert(error<=3e-5*scale);
        }
    }
    leo_fine_precision_free(&cache);leo_presence_destroy(w);free(samples);free(control);free(exact);
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int k=0;k<4;k++){check_rate(rates[k],0);check_rate(rates[k],1);}
    puts("folded fine FFT passed: direct DFT bins, negative wrap, full and partial inputs, all rates");
    return 0;
}
