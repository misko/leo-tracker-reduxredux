#ifndef LEO_FINE_REUSE_H
#define LEO_FINE_REUSE_H
#include <fftw3.h>
#ifndef LEO_FINE_BATCH
#define LEO_FINE_BATCH 4
#endif
#if LEO_FINE_BATCH != 4 && LEO_FINE_BATCH != 16
#error "LEO_FINE_BATCH must be 4 or 16"
#endif
typedef struct { int epoch,frames; double denominators[LEO_PRESENCE_FINE_FRAMES]; double complex *spectra[LEO_PRESENCE_FINE_FRAMES]; } leo_fine_reuse_entry;
typedef struct {
    size_t size; int count,transforms,hits;
    fftw_complex *batch_input,*batch_output; fftw_plan batch_plan;
    leo_fine_reuse_entry entries[LEO_FULL_SEARCH_MAX_CANDIDATES];
} leo_fine_reuse_cache;
static void leo_fine_reuse_init(leo_fine_reuse_cache *cache,size_t size)
{
    memset(cache,0,sizeof(*cache)); cache->size=size;
    cache->batch_input=fftw_alloc_complex((size_t)LEO_FINE_BATCH*size);
    cache->batch_output=fftw_alloc_complex((size_t)LEO_FINE_BATCH*size);
    if(cache->batch_input&&cache->batch_output){ int n=(int)size;
        cache->batch_plan=fftw_plan_many_dft(1,&n,LEO_FINE_BATCH,cache->batch_input,
            NULL,1,n,cache->batch_output,NULL,1,n,FFTW_FORWARD,FFTW_ESTIMATE); }
}
static void leo_fine_reuse_free(leo_fine_reuse_cache *cache)
{
    for(int i=0;i<cache->count;++i) for(int f=0;f<cache->entries[i].frames;++f) free(cache->entries[i].spectra[f]);
    if(cache->batch_plan)fftw_destroy_plan(cache->batch_plan);
    fftw_free(cache->batch_output); fftw_free(cache->batch_input); memset(cache,0,sizeof(*cache));
}
static int leo_fine_reuse_execute_batch(leo_fine_reuse_cache *cache,leo_fine_reuse_entry *item,int first,int lanes)
{
    if(lanes<LEO_FINE_BATCH) memset(cache->batch_input+(size_t)lanes*cache->size,0,
        (size_t)(LEO_FINE_BATCH-lanes)*cache->size*sizeof(fftw_complex));
    fftw_execute(cache->batch_plan);
    for(int lane=0;lane<lanes;++lane){
        double complex *p=malloc(cache->size*sizeof(*p)); if(!p)return -1;
        memcpy(p,cache->batch_output+(size_t)lane*cache->size,cache->size*sizeof(*p));
        item->spectra[first+lane]=p;
    }
    return 0;
}
static int leo_fine_reuse_scores(leo_presence_workspace *w,size_t sample_count,int epoch,double first_frequency,int frequency_count,double *scores,leo_fine_reuse_cache *cache)
{
    int entry=-1; for(int i=0;i<cache->count;++i)if(cache->entries[i].epoch==epoch){entry=i;break;}
    if(entry<0){
        if(!cache->batch_plan||cache->count>=LEO_FULL_SEARCH_MAX_CANDIDATES)return -1;
        entry=cache->count++; leo_fine_reuse_entry *item=&cache->entries[entry]; item->epoch=epoch;
        size_t last=(size_t)symbol_start(w,301)-1; double template_energy=0; memset(w->base,0,w->n*sizeof(*w->base));
        const int step=LEO_PRESENCE_FINE_ALL_SYMBOLS?1:2;
        for(int symbol=2;symbol<302;symbol+=step){int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);for(int k=begin;k<end;++k){template_energy+=power(w->exact[k]);w->base[k]=conj(w->exact[k]);}}
        int pending=0,first_pending=0;
        for(int frame=0;frame<LEO_PRESENCE_FINE_FRAMES;++frame){
            int start=frame_start(w,epoch,frame+w->acquisition_first_frame); if((size_t)start+last>=sample_count)break;
            double complex *input=(double complex *)cache->batch_input+(size_t)pending*cache->size;
            memset(input,0,cache->size*sizeof(*input)); double energy=0;
            for(int symbol=2;symbol<302;symbol+=step){int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);for(int k=begin;k<end;++k){energy+=power(w->samples[start+k]);input[k]=w->samples[start+k]*w->base[k];}}
            item->denominators[item->frames]=sqrt(template_energy*energy); ++item->frames;
            if(++pending==LEO_FINE_BATCH){if(leo_fine_reuse_execute_batch(cache,item,first_pending,pending)){leo_fine_reuse_free(cache);return -1;}first_pending=item->frames;pending=0;}
        }
        if(pending&&leo_fine_reuse_execute_batch(cache,item,first_pending,pending)){leo_fine_reuse_free(cache);return -1;}
        ++cache->transforms;
    }else ++cache->hits;
    int first_bin=(int)nearbyint(first_frequency/w->fine_step_hz); first_bin=(first_bin+(int)cache->size)%(int)cache->size;
    memset(scores,0,(size_t)frequency_count*sizeof(*scores)); leo_fine_reuse_entry *item=&cache->entries[entry];
    for(int frame=0;frame<item->frames;++frame){int bin=first_bin;if(item->denominators[frame]>0)for(int f=0;f<frequency_count;++f){scores[f]+=magnitude(item->spectra[frame][bin])/item->denominators[frame];if(++bin==(int)cache->size)bin=0;}}
    if(item->frames)
        for(int f=0;f<frequency_count;++f)scores[f]/=item->frames;
    return 0;
}
#endif
