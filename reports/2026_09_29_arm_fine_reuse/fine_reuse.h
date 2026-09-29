#ifndef LEO_FINE_REUSE_H
#define LEO_FINE_REUSE_H

/* Report-local, per-search-call cache.  An entry owns each valid frame's
 * complex FFT output and normalization denominator for one integer epoch.
 * Candidate requests evaluate only their original bins, preserving the
 * magnitude, frame-addition and final-division sequence of fine_scores(). */
typedef struct {
    int epoch;
    int frames;
    double denominators[LEO_PRESENCE_FINE_FRAMES];
    double complex *spectra[LEO_PRESENCE_FINE_FRAMES];
} leo_fine_reuse_entry;

typedef struct {
    size_t size;
    int count;
    int transforms;
    int hits;
    leo_fine_reuse_entry entries[LEO_FULL_SEARCH_MAX_CANDIDATES];
} leo_fine_reuse_cache;

static void leo_fine_reuse_init(leo_fine_reuse_cache *cache, size_t size)
{
    memset(cache, 0, sizeof(*cache));
    cache->size=size;
}

static void leo_fine_reuse_free(leo_fine_reuse_cache *cache)
{
    for (int i=0; i<cache->count; ++i)
        for (int frame=0; frame<cache->entries[i].frames; ++frame)
            free(cache->entries[i].spectra[frame]);
    memset(cache, 0, sizeof(*cache));
}

static int leo_fine_reuse_scores(leo_presence_workspace *w, size_t sample_count,
    int epoch, double first_frequency, int frequency_count, double *scores,
    leo_fine_reuse_cache *cache)
{
    int entry=-1;
    for (int i=0; i<cache->count; ++i)
        if (cache->entries[i].epoch==epoch) { entry=i; break; }
    if (entry<0) {
        if (cache->count>=LEO_FULL_SEARCH_MAX_CANDIDATES) return -1;
        entry=cache->count++;
        leo_fine_reuse_entry *item=&cache->entries[entry];
        item->epoch=epoch;
        size_t last=(size_t)symbol_start(w,301)-1;
        double template_energy=0;
        memset(w->base,0,w->n*sizeof(*w->base));
        const int step=LEO_PRESENCE_FINE_ALL_SYMBOLS ? 1 : 2;
        for (int symbol=2; symbol<302; symbol+=step) {
            int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
            for (int k=begin;k<end;++k) {
                template_energy+=power(w->exact[k]);
                w->base[k]=conj(w->exact[k]);
            }
        }
        for (int frame=0; frame<LEO_PRESENCE_FINE_FRAMES; ++frame) {
            int start=frame_start(w,epoch,frame+w->acquisition_first_frame);
            if ((size_t)start+last>=sample_count) break;
            memset(w->input,0,w->n*sizeof(*w->input));
            double energy=0;
            for (int symbol=2; symbol<302; symbol+=step) {
                int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
                for (int k=begin;k<end;++k) {
                    energy+=power(w->samples[start+k]);
                    w->input[k]=w->samples[start+k]*w->base[k];
                }
            }
            leo_fft_forward_range(&w->fine_fft,w->input,w->n,0,cache->size);
            item->spectra[item->frames]=malloc(cache->size*sizeof(double complex));
            if (!item->spectra[item->frames]) {
                leo_fine_reuse_free(cache); return -1;
            }
            memcpy(item->spectra[item->frames],w->fine_fft.output,
                cache->size*sizeof(double complex));
            item->denominators[item->frames]=sqrt(template_energy*energy);
            ++item->frames;
        }
        ++cache->transforms;
    } else ++cache->hits;

    int first_bin=(int)nearbyint(first_frequency/w->fine_step_hz);
    first_bin=(first_bin+(int)cache->size)%(int)cache->size;
    memset(scores,0,(size_t)frequency_count*sizeof(*scores));
    leo_fine_reuse_entry *item=&cache->entries[entry];
    for (int frame=0; frame<item->frames; ++frame) {
        int bin=first_bin;
        if (item->denominators[frame]>0)
            for (int f=0; f<frequency_count; ++f) {
                scores[f]+=magnitude(item->spectra[frame][bin])/item->denominators[frame];
                if (++bin==(int)cache->size) bin=0;
            }
    }
    if (item->frames)
        for (int f=0; f<frequency_count; ++f) scores[f]/=item->frames;
    return 0;
}

#endif
