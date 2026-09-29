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
    int frame_indices[LEO_PRESENCE_FINE_FRAMES];
    double denominators[LEO_PRESENCE_FINE_FRAMES];
    float complex *spectra[LEO_PRESENCE_FINE_FRAMES];
} leo_fine_precision_entry;

typedef struct leo_fine_precision_workspace {
    size_t size;
    fftwf_complex *input, *output;
    fftwf_plan plan;
} leo_fine_precision_workspace;

typedef struct {
    int count, transforms, hits, calls;
    int guard_checks, fallbacks, nonfinite_fallbacks;
    int near_tie_fallbacks, interpolation_fallbacks;
    leo_fine_precision_workspace local_workspace;
    leo_fine_precision_workspace *workspace;
    int owns_workspace;
    leo_fine_precision_entry entries[LEO_FULL_SEARCH_MAX_CANDIDATES];
} leo_fine_precision_cache;

/* Zero retains every available fine-frequency frame.  A positive budget is
 * applied only to the approximate fine estimator; final GLRT scoring is
 * unchanged. */
#ifndef LEO_FINE_FRAME_BUDGET_DEFAULT
#define LEO_FINE_FRAME_BUDGET_DEFAULT 0
#endif
static int leo_fine_precision_frame_budget=LEO_FINE_FRAME_BUDGET_DEFAULT;

static int leo_fine_precision_set_frame_budget(int frames)
{
    if(frames!=0 && frames!=1 && frames!=2 && frames!=4 && frames!=8) return -1;
    leo_fine_precision_frame_budget=frames;
    return 0;
}

/* Keep the stored FFT cells compact (two FP32 lanes), but perform the final
 * magnitude and score accumulation in FP64.  The explicit lanes also avoid a
 * libc complex-absolute call in the innermost scoring loop. */
static inline double leo_fine_precision_magnitude(const float complex value)
{
    const double re=(double)crealf(value), im=(double)cimagf(value);
    return sqrt(re*re+im*im);
}

static inline void *leo_fine_precision_spectrum_alloc(size_t bytes)
{
    void *storage=NULL;
    return posix_memalign(&storage,16,bytes)==0 ? storage : NULL;
}

static int leo_fine_precision_workspace_init(leo_fine_precision_workspace *workspace,
    size_t size)
{
    memset(workspace,0,sizeof(*workspace));workspace->size=size;
    workspace->input=fftwf_alloc_complex(size);
    workspace->output=fftwf_alloc_complex(size);
    if(workspace->input&&workspace->output)
        workspace->plan=fftwf_plan_dft_1d((int)size,workspace->input,workspace->output,
            FFTW_FORWARD,FFTW_ESTIMATE);
    if(workspace->plan)return 0;
    fftwf_free(workspace->input);fftwf_free(workspace->output);
    memset(workspace,0,sizeof(*workspace));
    return -1;
}

static void leo_fine_precision_workspace_free(leo_fine_precision_workspace *workspace)
{
    if(!workspace)return;
    if(workspace->plan)fftwf_destroy_plan(workspace->plan);
    fftwf_free(workspace->input);fftwf_free(workspace->output);
    memset(workspace,0,sizeof(*workspace));
}

static int leo_fine_precision_init(leo_fine_precision_cache *cache,size_t size,
    leo_fine_precision_workspace *workspace)
{
    memset(cache,0,sizeof(*cache));
    if(workspace){
        if(workspace->size!=size||!workspace->input||!workspace->output||!workspace->plan)
            return -1;
        cache->workspace=workspace;return 0;
    }
    if(leo_fine_precision_workspace_init(&cache->local_workspace,size))return -1;
    cache->workspace=&cache->local_workspace;cache->owns_workspace=1;return 0;
}

static void leo_fine_precision_free(leo_fine_precision_cache *cache)
{
    for (int i=0;i<cache->count;++i)
        for (int frame=0;frame<cache->entries[i].frames;++frame)
            free(cache->entries[i].spectra[frame]);
    if(cache->owns_workspace)leo_fine_precision_workspace_free(&cache->local_workspace);
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
        int available=0;
        while(available<LEO_PRESENCE_FINE_FRAMES) {
            int start=frame_start(w,epoch,available+w->acquisition_first_frame);
            if((size_t)start+last>=sample_count) break;
            ++available;
        }
        int selected=available;
        if(leo_fine_precision_frame_budget>0 && selected>leo_fine_precision_frame_budget)
            selected=leo_fine_precision_frame_budget;
        for(int slot=0;slot<selected;++slot) {
            int frame=selected==1 ? (available-1)/2 : slot*(available-1)/(selected-1);
            int start=frame_start(w,epoch,frame+w->acquisition_first_frame);
            leo_fine_precision_workspace *workspace=cache->workspace;
            memset(workspace->input,0,workspace->size*sizeof(*workspace->input));
            double energy=0;
            for(int symbol=2;symbol<302;symbol+=symbol_step) {
                int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
                for(int k=begin;k<end;++k) {
                    energy+=power(w->samples[start+k]);
                    const double ar=creal(w->samples[start+k]);
                    const double ai=cimag(w->samples[start+k]);
                    const double br=creal(w->base[k]);
                    const double bi=cimag(w->base[k]);
                    workspace->input[k]=(float)(ar*br-ai*bi)+I*(float)(ar*bi+ai*br);
                }
            }
            fftwf_execute(workspace->plan);
            item->spectra[item->frames]=(float complex *)leo_fine_precision_spectrum_alloc(
                workspace->size*sizeof(float complex));
            if(!item->spectra[item->frames]) {leo_fine_precision_free(cache);return -1;}
            memcpy(item->spectra[item->frames],workspace->output,
                workspace->size*sizeof(float complex));
            item->denominators[item->frames]=sqrt(template_energy*energy);
            item->frame_indices[item->frames]=frame;
            ++item->frames;
        }
        ++cache->transforms;
    } else ++cache->hits;
    int first_bin=(int)nearbyint(first_frequency/w->fine_step_hz);
    first_bin=(first_bin+(int)cache->workspace->size)%(int)cache->workspace->size;
    memset(scores,0,(size_t)frequency_count*sizeof(*scores));
    leo_fine_precision_entry *item=&cache->entries[entry];
    for(int frame=0;frame<item->frames;++frame) {
        int bin=first_bin;
        if(item->denominators[frame]>0) {
            const float complex *restrict spectrum=item->spectra[frame];
            double *restrict score_out=scores;
            const double reciprocal=1.0/item->denominators[frame];
            for(int f=0;f<frequency_count;++f) {
                score_out[f]+=leo_fine_precision_magnitude(spectrum[bin])*reciprocal;
                if(++bin==(int)cache->workspace->size) bin=0;
            }
        }
    }
    if(item->frames) for(int f=0;f<frequency_count;++f) scores[f]/=item->frames;
#if LEO_FINE_PRECISION_GUARDED
    ++cache->guard_checks;
    int reason=leo_fine_precision_guard(scores,first_frequency,w->fine_step_hz,frequency_count);
    if(reason) {
        ++cache->fallbacks;
        cache->nonfinite_fallbacks+=(reason&LEO_FINE_GUARD_NONFINITE)!=0;
        cache->near_tie_fallbacks+=(reason&LEO_FINE_GUARD_NEAR_TIE)!=0;
        cache->interpolation_fallbacks+=(reason&LEO_FINE_GUARD_INTERPOLATION)!=0;
        fine_scores(w,sample_count,epoch,first_frequency,frequency_count,scores);
    }
#endif
    return 0;
}
#endif
