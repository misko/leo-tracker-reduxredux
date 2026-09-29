#ifndef LEO_FINE_FIXED_H
#define LEO_FINE_FIXED_H
#include "fixed_fft.h"

typedef struct {
    int epoch,frames;
    double denominators[LEO_PRESENCE_FINE_FRAMES];
    double output_scale[LEO_PRESENCE_FINE_FRAMES];
    leo_qcomplex *spectra[LEO_PRESENCE_FINE_FRAMES];
} leo_fine_fixed_entry;

typedef struct {
    size_t size;
    int count,transforms,hits,calls;
    leo_fixed_fft fft;
    double complex *packing;
    leo_fine_fixed_entry entries[LEO_FULL_SEARCH_MAX_CANDIDATES];
} leo_fine_fixed_cache;

static int leo_fine_fixed_init(leo_fine_fixed_cache *cache,size_t size)
{
    memset(cache,0,sizeof(*cache)); cache->size=size;
    cache->packing=calloc(size,sizeof(*cache->packing));
    if(!cache->packing || leo_fixed_fft_init(&cache->fft,size)) return -1;
    return 0;
}

static void leo_fine_fixed_free(leo_fine_fixed_cache *cache)
{
    for(int i=0;i<cache->count;++i) for(int f=0;f<cache->entries[i].frames;++f)
        free(cache->entries[i].spectra[f]);
    leo_fixed_fft_free(&cache->fft); free(cache->packing); memset(cache,0,sizeof(*cache));
}

static int leo_fine_fixed_scores(leo_presence_workspace *w,size_t sample_count,
    int epoch,double first_frequency,int frequency_count,double *scores,
    leo_fine_fixed_cache *cache)
{
    ++cache->calls; int entry=-1;
    for(int i=0;i<cache->count;++i) if(cache->entries[i].epoch==epoch){entry=i;break;}
    if(entry<0) {
        if(cache->count>=LEO_FULL_SEARCH_MAX_CANDIDATES) return -1;
        entry=cache->count++; leo_fine_fixed_entry *item=&cache->entries[entry]; item->epoch=epoch;
        size_t last=(size_t)symbol_start(w,301)-1; double template_energy=0;
        memset(w->base,0,w->n*sizeof(*w->base));
        const int symbol_step=LEO_PRESENCE_FINE_ALL_SYMBOLS?1:2;
        for(int symbol=2;symbol<302;symbol+=symbol_step) {
            int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
            for(int k=begin;k<end;++k){template_energy+=power(w->exact[k]);w->base[k]=conj(w->exact[k]);}
        }
        for(int frame=0;frame<LEO_PRESENCE_FINE_FRAMES;++frame) {
            int start=frame_start(w,epoch,frame+w->acquisition_first_frame);
            if((size_t)start+last>=sample_count) break;
            memset(cache->packing,0,cache->size*sizeof(*cache->packing)); double energy=0;
            for(int symbol=2;symbol<302;symbol+=symbol_step) {
                int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
                for(int k=begin;k<end;++k){energy+=power(w->samples[start+k]);cache->packing[k]=w->samples[start+k]*w->base[k];}
            }
            item->output_scale[item->frames]=leo_fixed_fft_pack(&cache->fft,cache->packing);
            leo_fixed_fft_forward(&cache->fft);
            item->spectra[item->frames]=malloc(cache->size*sizeof(leo_qcomplex));
            if(!item->spectra[item->frames]){leo_fine_fixed_free(cache);return -1;}
            memcpy(item->spectra[item->frames],cache->fft.output,cache->size*sizeof(leo_qcomplex));
            item->denominators[item->frames]=sqrt(template_energy*energy); ++item->frames;
        }
        ++cache->transforms;
    } else ++cache->hits;
    int first_bin=(int)nearbyint(first_frequency/w->fine_step_hz);
    first_bin=(first_bin+(int)cache->size)%(int)cache->size;
    memset(scores,0,(size_t)frequency_count*sizeof(*scores)); leo_fine_fixed_entry *item=&cache->entries[entry];
    for(int frame=0;frame<item->frames;++frame) {
        int bin=first_bin;
        if(item->denominators[frame]>0) for(int f=0;f<frequency_count;++f) {
            double re=leo_qre(item->spectra[frame][bin]),im=leo_qim(item->spectra[frame][bin]);
            scores[f]+=hypot(re,im)*item->output_scale[frame]/item->denominators[frame];
            if(++bin==(int)cache->size)bin=0;
        }
    }
    if(item->frames)for(int f=0;f<frequency_count;++f)scores[f]/=item->frames;
    return 0;
}
#endif
