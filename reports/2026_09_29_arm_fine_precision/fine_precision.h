#ifndef LEO_FINE_PRECISION_H
#define LEO_FINE_PRECISION_H

#include <float.h>
#include <fftw3.h>

#ifndef LEO_FINE_PRECISION_GUARDED
#define LEO_FINE_PRECISION_GUARDED 0
#endif

/* Fixed before cohort evaluation. Scores are normalized correlations and are
 * ordinarily O(1). This is deliberately a conservative engineering screen,
 * not a proved FFT error bound. */
#define LEO_FINE_PRECISION_GUARD_ULPS 256.0

enum {
    LEO_FINE_GUARD_NONFINITE = 1,
    LEO_FINE_GUARD_NEAR_TIE = 2,
    LEO_FINE_GUARD_INTERPOLATION = 4
};

typedef struct {
    int epoch;
    int frames;
    double denominators[LEO_PRESENCE_FINE_FRAMES];
    float complex *spectra[LEO_PRESENCE_FINE_FRAMES];
} leo_fine_precision_entry;

typedef struct {
    size_t size;
    int count, transforms, hits, calls;
    int guard_checks, fallbacks, nonfinite_fallbacks;
    int near_tie_fallbacks, interpolation_fallbacks;
    double plan_ms, preparation_ms, execute_ms, storage_ms;
    double score_ms, guard_ms, recompute_ms;
    fftwf_complex *input, *output;
    fftwf_plan plan;
    leo_fine_precision_entry entries[LEO_FULL_SEARCH_MAX_CANDIDATES];
} leo_fine_precision_cache;

static int leo_fine_precision_init(leo_fine_precision_cache *cache, size_t size)
{
    double started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    memset(cache, 0, sizeof(*cache));
    cache->size=size;
    cache->input=fftwf_alloc_complex(size);
    cache->output=fftwf_alloc_complex(size);
    if (cache->input && cache->output)
        cache->plan=fftwf_plan_dft_1d((int)size,cache->input,cache->output,
            FFTW_FORWARD,FFTW_ESTIMATE);
    cache->plan_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    if (cache->plan) return 0;
    fftwf_free(cache->input); fftwf_free(cache->output);
    memset(cache,0,sizeof(*cache));
    return -1;
}

static void leo_fine_precision_free(leo_fine_precision_cache *cache)
{
    for (int i=0;i<cache->count;++i)
        for (int frame=0;frame<cache->entries[i].frames;++frame)
            free(cache->entries[i].spectra[frame]);
    if (cache->plan) fftwf_destroy_plan(cache->plan);
    fftwf_free(cache->input); fftwf_free(cache->output);
    memset(cache,0,sizeof(*cache));
}

static int leo_fine_precision_best(const double *scores, double first,
    double step, int n)
{
    int best=0;
    for (int k=1;k<n;++k) {
        double fk=first+k*step, fb=first+best*step;
        if (scores[k]>scores[best] || (scores[k]==scores[best] &&
            (fabs(fk)<fabs(fb) || (fabs(fk)==fabs(fb) && fk<fb)))) best=k;
    }
    return best;
}

static int leo_fine_precision_guard(const double *scores, double first,
    double step, int n)
{
    int reason=0;
    for (int k=0;k<n;++k) if (!isfinite(scores[k])) reason|=LEO_FINE_GUARD_NONFINITE;
    int best=leo_fine_precision_best(scores,first,step,n), second=-1;
    for (int k=0;k<n;++k) if (k!=best && (second<0 || scores[k]>scores[second])) second=k;
    double scale=fmax(1.0,fabs(scores[best]));
    double tolerance=LEO_FINE_PRECISION_GUARD_ULPS*FLT_EPSILON*scale;
    if (second>=0 && scores[best]-scores[second]<=tolerance)
        reason|=LEO_FINE_GUARD_NEAR_TIE;
    if (best>0 && best+1<n) {
        double left=scores[best-1], center=scores[best], right=scores[best+1];
        double curve=left-2*center+right, numerator=left-right;
        /* A shallow parabola or an offset within 10% of the one-bin clamp is
         * sensitive to small score perturbations, including a stable/flat
         * branch change at the original curve < -1e-15 test. */
        if (!isfinite(curve) || fabs(curve)<=tolerance ||
            (curve<0 && fabs(numerator)>=1.8*fabs(curve)))
            reason|=LEO_FINE_GUARD_INTERPOLATION;
    }
    return reason;
}

static int leo_fine_precision_scores(leo_presence_workspace *w,
    size_t sample_count,int epoch,double first_frequency,int frequency_count,
    double *scores,leo_fine_precision_cache *cache)
{
    ++cache->calls;
    int entry=-1;
    for (int i=0;i<cache->count;++i)
        if (cache->entries[i].epoch==epoch) {entry=i;break;}
    if (entry<0) {
        double preparation_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        if (cache->count>=LEO_FULL_SEARCH_MAX_CANDIDATES) return -1;
        entry=cache->count++;
        leo_fine_precision_entry *item=&cache->entries[entry]; item->epoch=epoch;
        size_t last=(size_t)symbol_start(w,301)-1;
        double template_energy=0;
        memset(w->base,0,w->n*sizeof(*w->base));
        const int symbol_step=LEO_PRESENCE_FINE_ALL_SYMBOLS ? 1 : 2;
        for(int symbol=2;symbol<302;symbol+=symbol_step) {
            int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
            for(int k=begin;k<end;++k) {template_energy+=power(w->exact[k]);w->base[k]=conj(w->exact[k]);}
        }
        cache->preparation_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-preparation_started;
        for(int frame=0;frame<LEO_PRESENCE_FINE_FRAMES;++frame) {
            int start=frame_start(w,epoch,frame+w->acquisition_first_frame);
            if((size_t)start+last>=sample_count) break;
            preparation_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
            memset(cache->input,0,cache->size*sizeof(*cache->input));
            double energy=0;
            for(int symbol=2;symbol<302;symbol+=symbol_step) {
                int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
                for(int k=begin;k<end;++k) {
                    energy+=power(w->samples[start+k]);
                    double complex value=w->samples[start+k]*w->base[k];
                    cache->input[k]=(float)creal(value)+I*(float)cimag(value);
                }
            }
            cache->preparation_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-preparation_started;
            double execute_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
            fftwf_execute(cache->plan);
            cache->execute_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-execute_started;
            double storage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
            item->spectra[item->frames]=malloc(cache->size*sizeof(float complex));
            if(!item->spectra[item->frames]) {leo_fine_precision_free(cache);return -1;}
            memcpy(item->spectra[item->frames],cache->output,cache->size*sizeof(float complex));
            item->denominators[item->frames]=sqrt(template_energy*energy); ++item->frames;
            cache->storage_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-storage_started;
        }
        ++cache->transforms;
    } else ++cache->hits;
    double score_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    int first_bin=(int)nearbyint(first_frequency/w->fine_step_hz);
    first_bin=(first_bin+(int)cache->size)%(int)cache->size;
    memset(scores,0,(size_t)frequency_count*sizeof(*scores));
    leo_fine_precision_entry *item=&cache->entries[entry];
    for(int frame=0;frame<item->frames;++frame) {
        int bin=first_bin;
        if(item->denominators[frame]>0) for(int f=0;f<frequency_count;++f) {
            scores[f]+=(double)cabsf(item->spectra[frame][bin])/item->denominators[frame];
            if(++bin==(int)cache->size) bin=0;
        }
    }
    if(item->frames) for(int f=0;f<frequency_count;++f) scores[f]/=item->frames;
    cache->score_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-score_started;
#if LEO_FINE_PRECISION_GUARDED
    double guard_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    ++cache->guard_checks;
    int reason=leo_fine_precision_guard(scores,first_frequency,w->fine_step_hz,frequency_count);
    cache->guard_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-guard_started;
    if(reason) {
        ++cache->fallbacks;
        cache->nonfinite_fallbacks+=(reason&LEO_FINE_GUARD_NONFINITE)!=0;
        cache->near_tie_fallbacks+=(reason&LEO_FINE_GUARD_NEAR_TIE)!=0;
        cache->interpolation_fallbacks+=(reason&LEO_FINE_GUARD_INTERPOLATION)!=0;
        double recompute_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        fine_scores(w,sample_count,epoch,first_frequency,frequency_count,scores);
        cache->recompute_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-recompute_started;
    }
#endif
    return 0;
}
#endif
