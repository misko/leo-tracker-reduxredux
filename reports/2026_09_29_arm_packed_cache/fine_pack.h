#ifndef LEO_FINE_PACK_H
#define LEO_FINE_PACK_H

#include <fftw3.h>
#include <stdint.h>
#if defined(LEO_FINE_PACK_NEON) && defined(__ARM_NEON)
#include <arm_neon.h>
#endif

typedef struct { int16_t re, im; } leo_fine_pack_complex;

typedef struct {
    int epoch;
    int frames;
    double denominators[LEO_PRESENCE_FINE_FRAMES];
    float scales[LEO_PRESENCE_FINE_FRAMES];
    leo_fine_pack_complex *spectra[LEO_PRESENCE_FINE_FRAMES];
} leo_fine_pack_entry;

typedef struct {
    size_t size;
    int count, transforms, hits, calls;
    uint64_t frames, values, bytes, zero_frames, clipped_values;
    double scale_scan_ms, packing_ms, dequant_ms;
    fftwf_complex *input, *output;
    fftwf_plan plan;
    leo_fine_pack_entry entries[LEO_FULL_SEARCH_MAX_CANDIDATES];
} leo_fine_pack_cache;

static int leo_fine_pack_init(leo_fine_pack_cache *cache, size_t size)
{
    memset(cache,0,sizeof(*cache)); cache->size=size;
    cache->input=fftwf_alloc_complex(size); cache->output=fftwf_alloc_complex(size);
    if(cache->input&&cache->output) cache->plan=fftwf_plan_dft_1d((int)size,
        cache->input,cache->output,FFTW_FORWARD,FFTW_ESTIMATE);
    if(cache->plan) return 0;
    fftwf_free(cache->input); fftwf_free(cache->output); memset(cache,0,sizeof(*cache));
    return -1;
}

static void leo_fine_pack_free(leo_fine_pack_cache *cache)
{
    for(int i=0;i<cache->count;++i) for(int frame=0;frame<cache->entries[i].frames;++frame)
        free(cache->entries[i].spectra[frame]);
    if(cache->plan) fftwf_destroy_plan(cache->plan);
    fftwf_free(cache->input); fftwf_free(cache->output); memset(cache,0,sizeof(*cache));
}

static int16_t leo_fine_pack_quantize(float value,float reciprocal,uint64_t *clipped)
{
    float scaled=value*reciprocal;
    if(scaled>32767.0f){scaled=32767.0f;++*clipped;}
    if(scaled< -32767.0f){scaled=-32767.0f;++*clipped;}
    return (int16_t)nearbyintf(scaled);
}

#if defined(LEO_FINE_PACK_NEON) && defined(__ARM_NEON)
/* Round four finite Q15-range floats exactly as nearbyintf under the default
 * round-to-nearest-even mode. ARMv7 vcvt truncates, so first use the binary32
 * magic-bias operation to produce integral floats. */
static int16x4_t leo_fine_pack_quantize4(float32x4_t value,float32x4_t reciprocal,
    uint64_t *clipped)
{
    float32x4_t scaled=vmulq_f32(value,reciprocal);
    const float32x4_t high=vdupq_n_f32(32767.0f),low=vdupq_n_f32(-32767.0f);
    uint32x4_t outside=vorrq_u32(vcgtq_f32(scaled,high),vcltq_f32(scaled,low));
    uint32_t lanes[4];vst1q_u32(lanes,outside);
    *clipped+=(lanes[0]>>31)+(lanes[1]>>31)+(lanes[2]>>31)+(lanes[3]>>31);
    scaled=vmaxq_f32(low,vminq_f32(high,scaled));
    const uint32x4_t sign=vandq_u32(vreinterpretq_u32_f32(scaled),vdupq_n_u32(0x80000000u));
    const float32x4_t magic=vreinterpretq_f32_u32(vorrq_u32(sign,vdupq_n_u32(0x4b400000u)));
    float32x4_t integral=vsubq_f32(vaddq_f32(scaled,magic),magic);
    return vmovn_s32(vcvtq_s32_f32(integral));
}
#endif

static int leo_fine_pack_scores(leo_presence_workspace *w,size_t sample_count,
    int epoch,double first_frequency,int frequency_count,double *scores,
    leo_fine_pack_cache *cache)
{
    ++cache->calls;
    int entry=-1;
    for(int i=0;i<cache->count;++i) if(cache->entries[i].epoch==epoch){entry=i;break;}
    if(entry<0){
        if(cache->count>=LEO_FULL_SEARCH_MAX_CANDIDATES) return -1;
        entry=cache->count++; leo_fine_pack_entry *item=&cache->entries[entry]; item->epoch=epoch;
        size_t last=(size_t)symbol_start(w,301)-1; double template_energy=0;
        memset(w->base,0,w->n*sizeof(*w->base));
        const int symbol_step=LEO_PRESENCE_FINE_ALL_SYMBOLS?1:2;
        for(int symbol=2;symbol<302;symbol+=symbol_step){
            int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
            for(int k=begin;k<end;++k){template_energy+=power(w->exact[k]);w->base[k]=conj(w->exact[k]);}
        }
        for(int frame=0;frame<LEO_PRESENCE_FINE_FRAMES;++frame){
            int start=frame_start(w,epoch,frame+w->acquisition_first_frame);
            if((size_t)start+last>=sample_count) break;
            memset(cache->input,0,cache->size*sizeof(*cache->input)); double energy=0;
            for(int symbol=2;symbol<302;symbol+=symbol_step){
                int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
                for(int k=begin;k<end;++k){energy+=power(w->samples[start+k]);
                    double complex value=w->samples[start+k]*w->base[k];
                    cache->input[k]=(float)creal(value)+I*(float)cimag(value);
                }
            }
            fftwf_execute(cache->plan);
            double tick=clock_ms(CLOCK_PROCESS_CPUTIME_ID); float peak=0;
#if defined(LEO_FINE_PACK_NEON) && defined(__ARM_NEON)
            {
            const float *components=(const float *)cache->output;size_t component_count=2*cache->size,k=0;
            float32x4_t vector_peak=vdupq_n_f32(0.0f);
            for(;k+4<=component_count;k+=4)vector_peak=vmaxq_f32(vector_peak,vabsq_f32(vld1q_f32(components+k)));
            float32x2_t half=vmax_f32(vget_low_f32(vector_peak),vget_high_f32(vector_peak));
            half=vpmax_f32(half,half);peak=vget_lane_f32(half,0);
            for(;k<component_count;++k){float value=fabsf(components[k]);if(value>peak)peak=value;}
            }
#else
            for(size_t k=0;k<cache->size;++k){
                float ar=fabsf(crealf(cache->output[k])),ai=fabsf(cimagf(cache->output[k]));
                if(ar>peak)peak=ar;
                if(ai>peak)peak=ai;
            }
#endif
            cache->scale_scan_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-tick;
            tick=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
            leo_fine_pack_complex *packed=malloc(cache->size*sizeof(*packed));
            if(!packed){leo_fine_pack_free(cache);return -1;}
            float scale=peak>0?peak/32767.0f:0.0f, reciprocal=peak>0?32767.0f/peak:0.0f;
#if defined(LEO_FINE_PACK_NEON) && defined(__ARM_NEON)
            {
            const float *source=(const float *)cache->output;int16_t *destination=(int16_t *)packed;
            size_t component_count=2*cache->size,k=0;float32x4_t reciprocal4=vdupq_n_f32(reciprocal);
            for(;k+4<=component_count;k+=4)
                vst1_s16(destination+k,leo_fine_pack_quantize4(vld1q_f32(source+k),reciprocal4,&cache->clipped_values));
            for(;k<component_count;++k)destination[k]=leo_fine_pack_quantize(source[k],reciprocal,&cache->clipped_values);
            }
#else
            for(size_t k=0;k<cache->size;++k){
                packed[k].re=leo_fine_pack_quantize(crealf(cache->output[k]),reciprocal,&cache->clipped_values);
                packed[k].im=leo_fine_pack_quantize(cimagf(cache->output[k]),reciprocal,&cache->clipped_values);
            }
#endif
            item->spectra[item->frames]=packed; item->scales[item->frames]=scale;
            item->denominators[item->frames]=sqrt(template_energy*energy); ++item->frames;
            ++cache->frames; cache->values+=2*cache->size; cache->bytes+=cache->size*sizeof(*packed)+sizeof(scale);
            cache->zero_frames+=peak==0; cache->packing_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-tick;
        }
        ++cache->transforms;
    }else ++cache->hits;
    double tick=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    int first_bin=(int)nearbyint(first_frequency/w->fine_step_hz);
    first_bin=(first_bin+(int)cache->size)%(int)cache->size;
    memset(scores,0,(size_t)frequency_count*sizeof(*scores)); leo_fine_pack_entry *item=&cache->entries[entry];
    for(int frame=0;frame<item->frames;++frame){
        int bin=first_bin; double reciprocal=item->denominators[frame]>0?1.0/item->denominators[frame]:0;
        if(reciprocal) for(int f=0;f<frequency_count;++f){
            leo_fine_pack_complex q=item->spectra[frame][bin];
            double re=(double)q.re*item->scales[frame],im=(double)q.im*item->scales[frame];
            scores[f]+=hypot(re,im)*reciprocal;if(++bin==(int)cache->size)bin=0;
        }
    }
    if(item->frames)for(int f=0;f<frequency_count;++f)scores[f]/=item->frames;
    cache->dequant_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-tick; return 0;
}
#endif
