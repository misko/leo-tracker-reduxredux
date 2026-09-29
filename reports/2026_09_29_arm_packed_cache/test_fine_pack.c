static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t rng=0x159ad21bu;
static double random_value(void){rng=1664525u*rng+1013904223u;return ((rng>>8)*0x1p-23-1)*.5;}

static void test_quantizer(void)
{
    uint64_t clipped=0;
    assert(leo_fine_pack_quantize(1.0f,32767.0f,&clipped)==32767);
    assert(leo_fine_pack_quantize(-1.0f,32767.0f,&clipped)==-32767);
    assert(leo_fine_pack_quantize(2.0f,32767.0f,&clipped)==32767);
    assert(leo_fine_pack_quantize(-2.0f,32767.0f,&clipped)==-32767);
    assert(clipped==2);
}

#if defined(LEO_FINE_PACK_NEON) && defined(__ARM_NEON)
static void compare_quantize4(const float values[4],float reciprocal)
{
    uint64_t scalar_clipped=0,vector_clipped=0;int16_t scalar[4],vector[4];
    for(int k=0;k<4;++k)scalar[k]=leo_fine_pack_quantize(values[k],reciprocal,&scalar_clipped);
    vst1_s16(vector,leo_fine_pack_quantize4(vld1q_f32(values),vdupq_n_f32(reciprocal),&vector_clipped));
    assert(!memcmp(scalar,vector,sizeof(scalar)));assert(scalar_clipped==vector_clipped);
}

static void test_neon_quantizer(void)
{
    const float ties[][4]={{.5f,1.5f,2.5f,3.5f},{-.5f,-1.5f,-2.5f,-3.5f},
        {32767.0f,-32767.0f,32767.25f,-32767.25f},{32767.75f,-32767.75f,0.0f,-0.0f}};
    for(size_t k=0;k<sizeof(ties)/sizeof(ties[0]);++k)compare_quantize4(ties[k],1.0f);
    uint32_t state=0x62f39a1du;
    for(int trial=0;trial<10000;++trial){float values[4];
        for(int lane=0;lane<4;++lane){state=1664525u*state+1013904223u;
            values[lane]=((int32_t)(state>>8))*0x1p-8f;}
        state=1664525u*state+1013904223u;float reciprocal=(float)((state>>8)+1)*0x1p-24f;
        compare_quantize4(values,reciprocal);
    }
}
#endif

static void run_rate(uint32_t rate,int partial,int zero)
{
    size_t n=(rate+375)/750,count=partial?(size_t)ceil(rate/375.0):rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));assert(exact&&control&&samples);
    for(size_t k=0;k<n;++k){exact[k]=(leo_presence_complex){random_value(),random_value()};control[k]=(leo_presence_complex){random_value(),random_value()};}
    if(!zero)for(size_t k=0;k<count;++k)samples[k]=(leo_presence_complex){random_value(),random_value()};
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);assert(w&&!ingest(w,samples,count));
    w->acquisition_first_frame=0;int epoch=partial?0:(int)n/3,bins=129;double fp32[129],packed[129];
    fine_scores(w,count,epoch,-240000.0,bins,fp32);
    leo_fine_pack_cache cache;assert(!leo_fine_pack_init(&cache,w->fine_fft.size));
    assert(!leo_fine_pack_scores(w,count,epoch,-240000.0,bins,packed,&cache));
    assert(cache.count==1&&cache.transforms==1&&cache.calls==1);
    for(int k=0;k<bins;++k){assert(isfinite(packed[k]));assert(fabs(packed[k]-fp32[k])<=3e-5*fmax(1.0,fabs(fp32[k])));}
    assert(!leo_fine_pack_scores(w,count,epoch,80000.0,33,packed,&cache));
    assert(cache.count==1&&cache.transforms==1&&cache.hits==1&&cache.calls==2);
    if(zero)assert(cache.zero_frames==cache.frames);else assert(cache.bytes==cache.frames*(cache.size*sizeof(leo_fine_pack_complex)+sizeof(float)));
    /* At most the component establishing each frame scale can round a hair
     * beyond 32767; the saturating path must keep that from wrapping. */
    assert(cache.clipped_values<=cache.frames);
    leo_fine_pack_free(&cache);leo_presence_destroy(w);free(samples);free(control);free(exact);
}

int main(void)
{
    test_quantizer();
#if defined(LEO_FINE_PACK_NEON) && defined(__ARM_NEON)
    test_neon_quantizer();
#endif
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int i=0;i<4;++i){run_rate(rates[i],0,0);run_rate(rates[i],1,0);run_rate(rates[i],1,1);}
    puts("fine pack passed: Q15 block-floating cache, overflow, zero/partial frames, all rates");return 0;
}
