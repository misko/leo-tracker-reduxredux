/* Research-private FP32 fine-FFT screen with guarded FP64 bin verification.
 * This file is included after presence.c and is not a standalone translation
 * unit. The guard is empirically qualified, not a formal roundoff bound. */
#include <fftw3.h>

#define FINE_SCREEN_MAX_BINS 321
#define FINE_SCREEN_VERIFY_LIMIT 64
#define FINE_SCREEN_GUARD (256.0*FLT_EPSILON)

typedef struct {
    size_t size;
    fftwf_complex *input;
    fftwf_complex *output;
    fftwf_plan plan;
} fine_screen_plan;

static fine_screen_plan fine_plans[4];
static int fine_cleanup_registered;

static void fine_screen_cleanup(void)
{
    for (size_t i=0;i<4;++i) {
        if (fine_plans[i].plan) fftwf_destroy_plan(fine_plans[i].plan);
        if (fine_plans[i].input) fftwf_free(fine_plans[i].input);
        if (fine_plans[i].output) fftwf_free(fine_plans[i].output);
        fine_plans[i]=(fine_screen_plan){0};
    }
}

static fine_screen_plan *fine_screen_plan_for(size_t size)
{
    for (size_t i=0;i<4;++i) if (fine_plans[i].size==size) return &fine_plans[i];
    for (size_t i=0;i<4;++i) if (!fine_plans[i].size) {
        fine_screen_plan *p=&fine_plans[i];
        p->size=size;
        p->input=fftwf_alloc_complex(size);
        p->output=fftwf_alloc_complex(size);
        if (p->input && p->output)
            p->plan=fftwf_plan_dft_1d((int)size,p->input,p->output,
                FFTW_FORWARD,FFTW_ESTIMATE);
        if (!p->plan) { fine_screen_cleanup(); return NULL; }
        if (!fine_cleanup_registered) {
            if (atexit(fine_screen_cleanup)) { fine_screen_cleanup(); return NULL; }
            fine_cleanup_registered=1;
        }
        return p;
    }
    return NULL;
}

static double fine_exact_bin(leo_presence_workspace *w,size_t count,int epoch,
    int bin,double template_energy)
{
    double score=0;
    int frames=0;
    double angle=-TAU*bin/w->fine_fft.size;
    double complex root=cos(angle)+I*sin(angle);
    for (int frame=0;frame<LEO_PRESENCE_FINE_FRAMES;++frame) {
        int start=frame_start(w,epoch,frame+w->acquisition_first_frame);
        if ((size_t)start+(size_t)symbol_start(w,301)-1>=count) break;
        double energy=0;
        double complex total=0;
        for (int symbol=2;symbol<302;symbol+=
            (LEO_PRESENCE_FINE_ALL_SYMBOLS ? 1 : 2)) {
            int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
            double complex phase=cos(angle*begin)+I*sin(angle*begin);
            for (int k=begin;k<end;++k) {
                /* The original normalizer includes the complete selected
                 * symbol support, including cells whose template is zero. */
                energy+=power(w->samples[start+k]);
                total+=w->samples[start+k]*w->base[k]*phase;
                phase*=root;
            }
        }
        double denom=sqrt(template_energy*energy);
        if (denom>0) score+=magnitude(total)/denom;
        ++frames;
    }
    return frames ? score/frames : 0;
}

static void fine_scores_screen(leo_presence_workspace *w,size_t count,int epoch,
    double first_frequency,int frequency_count,double *scores,
    int *screened,int *rechecked,int *fallbacks)
{
    if (frequency_count<=0 || frequency_count>FINE_SCREEN_MAX_BINS) {
        ++*fallbacks; fine_scores(w,count,epoch,first_frequency,frequency_count,scores); return;
    }
    fine_screen_plan *plan=fine_screen_plan_for(w->fine_fft.size);
    if (!plan) { ++*fallbacks; fine_scores(w,count,epoch,first_frequency,frequency_count,scores); return; }
    size_t last=(size_t)symbol_start(w,301)-1;
    double template_energy=0;
    memset(w->base,0,w->n*sizeof(*w->base));
    memset(scores,0,(size_t)frequency_count*sizeof(*scores));
    const int step=LEO_PRESENCE_FINE_ALL_SYMBOLS ? 1 : 2;
    int first_bin=(int)nearbyint(first_frequency/w->fine_step_hz);
    first_bin=(first_bin+(int)w->fine_fft.size)%(int)w->fine_fft.size;
    for (int symbol=2;symbol<302;symbol+=step) {
        int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
        for (int k=begin;k<end;++k) {
            template_energy+=power(w->exact[k]);
            w->base[k]=conj(w->exact[k]);
        }
    }
    int frames=0;
    for (int frame=0;frame<LEO_PRESENCE_FINE_FRAMES;++frame) {
        int start=frame_start(w,epoch,frame+w->acquisition_first_frame);
        if ((size_t)start+last>=count) break;
        memset(plan->input,0,w->fine_fft.size*sizeof(*plan->input));
        double energy=0;
        for (int symbol=2;symbol<302;symbol+=step) {
            int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
            for (int k=begin;k<end;++k) {
                energy+=power(w->samples[start+k]);
                double complex value=w->samples[start+k]*w->base[k];
                plan->input[k]=(float)creal(value)+I*(float)cimag(value);
            }
        }
        fftwf_execute(plan->plan);
        double denom=sqrt(template_energy*energy);
        if (denom>0) for (int f=0,bin=first_bin;f<frequency_count;++f) {
            scores[f]+=hypot((double)crealf(plan->output[bin]),
                (double)cimagf(plan->output[bin]))/denom;
            if (++bin==(int)w->fine_fft.size) bin=0;
        }
        ++frames;
    }
    if (frames) for (int f=0;f<frequency_count;++f) scores[f]/=frames;
    *screened+=frequency_count;
    /* FP32 ties are resolved only after FP64 verification, so first locate
     * the numeric maximum without applying the final frequency tie-break. */
    int approximate=0;
    for (int f=1;f<frequency_count;++f) if (scores[f]>scores[approximate]) approximate=f;
    double guard=FINE_SCREEN_GUARD*fmax(1.0,scores[approximate]);
    unsigned char verify[FINE_SCREEN_MAX_BINS]={0};
    for (int f=0;f<frequency_count;++f) if (!isfinite(scores[f]) ||
        scores[f]>=scores[approximate]-guard)
        for (int d=-1;d<=1;++d) if (f+d>=0 && f+d<frequency_count) verify[f+d]=1;
    int verify_count=0;
    for (int f=0;f<frequency_count;++f) verify_count+=verify[f];
    if (verify_count>FINE_SCREEN_VERIFY_LIMIT) {
        ++*fallbacks; fine_scores(w,count,epoch,first_frequency,frequency_count,scores); return;
    }
    for (int f=0;f<frequency_count;++f) {
        if (!verify[f]) { scores[f]=-INFINITY; continue; }
        int bin=first_bin+f;
        if (bin>=(int)w->fine_fft.size) bin-=(int)w->fine_fft.size;
        scores[f]=fine_exact_bin(w,count,epoch,bin,template_energy);
        ++*rechecked;
    }
}
