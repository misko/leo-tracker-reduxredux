/* One process-local, bounded cache containing solely frozen reference material. */
enum { kernel_cache_slots=4 };

typedef struct {
    double rate, frequencies[21], inverse_ref[22];
    double complex refs[22][maximum_taps];
    int taps[22], anchors, lanes;
    unsigned long used;
    fftwf_complex *filters, *input, *spectrum, *inverse_input, *output;
    fftwf_plan forward, inverse;
} kernel_cache_entry;

static kernel_cache_entry workspace[kernel_cache_slots];
static unsigned long cache_clock;

static void destroy_kernel_entry(kernel_cache_entry *entry)
{
    if(entry->forward) fftwf_destroy_plan(entry->forward);
    if(entry->inverse) fftwf_destroy_plan(entry->inverse);
    fftwf_free(entry->filters);
    fftwf_free(entry->input);
    fftwf_free(entry->spectrum);
    fftwf_free(entry->inverse_input);
    fftwf_free(entry->output);
    memset(entry,0,sizeof(*entry));
}

void capture_kernel_clear(void)
{
    if(pthread_mutex_lock(&planner)) return;
    for(int i=0;i<kernel_cache_slots;++i) destroy_kernel_entry(&workspace[i]);
    cache_clock=0;
    pthread_mutex_unlock(&planner);
}

static int matches_kernel(const kernel_cache_entry *entry, const FoldedAnchorGridKernel *k,
    const int *taps)
{
    if(!entry->forward || entry->rate!=k->sample_rate_hz || entry->anchors!=k->symbol_count ||
        entry->lanes!=k->cfo_count || memcmp(entry->frequencies,k->frequencies,
            (size_t)k->cfo_count*sizeof(double)) ||
        memcmp(entry->taps,taps,(size_t)k->symbol_count*sizeof(int))) return 0;
    for(int s=0;s<entry->anchors;++s)
        if(memcmp(entry->refs[s],k->references+k->starts[s],(size_t)taps[s]*sizeof(double complex)))
            return 0;
    return 1;
}

static kernel_cache_entry *prepare_kernel(const FoldedAnchorGridKernel *k, const int *taps,
    int *built)
{
    kernel_cache_entry *target=&workspace[0];
    for(int i=0;i<kernel_cache_slots;++i) {
        kernel_cache_entry *entry=&workspace[i];
        if(matches_kernel(entry,k,taps)) {
            entry->used=++cache_clock;
            *built=0;
            return entry;
        }
        if(entry->used<target->used) target=entry;
    }
    destroy_kernel_entry(target);
    const int length=fft_length, ns=k->symbol_count, nf=k->cfo_count;
    const size_t batch=(size_t)nf*fft_length;
    target->filters=fftwf_alloc_complex((size_t)ns*batch);
    target->input=fftwf_alloc_complex(fft_length);
    target->spectrum=fftwf_alloc_complex(fft_length);
    target->inverse_input=fftwf_alloc_complex(batch);
    target->output=fftwf_alloc_complex(batch);
    if(!target->filters || !target->input || !target->spectrum || !target->inverse_input ||
        !target->output) goto error;
    target->forward=fftwf_plan_dft_1d(fft_length,target->input,target->spectrum,
        FFTW_FORWARD,FFTW_ESTIMATE);
    target->inverse=fftwf_plan_many_dft(1,&length,nf,target->inverse_input,NULL,1,fft_length,
        target->output,NULL,1,fft_length,FFTW_BACKWARD,FFTW_ESTIMATE);
    if(!target->forward || !target->inverse) goto error;
    target->rate=k->sample_rate_hz;
    target->anchors=ns;
    target->lanes=nf;
    memcpy(target->frequencies,k->frequencies,(size_t)nf*sizeof(double));
    memcpy(target->taps,taps,(size_t)ns*sizeof(int));
    double sine[21][maximum_taps], cosine[21][maximum_taps];
    for(int f=0;f<nf;++f) for(int j=0;j<maximum_taps;++j) {
        const double angle=6.283185307179586476925286766559*k->frequencies[f]*j/k->sample_rate_hz;
        sine[f][j]=sin(angle);
        cosine[f][j]=cos(angle);
    }
    for(int s=0;s<ns;++s) {
        double energy=0;
        memcpy(target->refs[s],k->references+k->starts[s],(size_t)taps[s]*sizeof(double complex));
        for(int j=0;j<taps[s];++j) {
            const double a=creal(target->refs[s][j]), b=cimag(target->refs[s][j]);
            energy+=a*a+b*b;
        }
        target->inverse_ref[s]=energy>0 ? 1/sqrt(energy) : 0;
        for(int f=0;f<nf;++f) {
            memset(target->input,0,fft_length*sizeof(fftwf_complex));
            for(int t=0;t<taps[s];++t) {
                const double real=creal(target->refs[s][t]), imag=cimag(target->refs[s][t]);
                const int j=taps[s]-1-t;
                target->input[j][0]=(float)(real*cosine[f][t]-imag*sine[f][t]);
                target->input[j][1]=(float)-(real*sine[f][t]+imag*cosine[f][t]);
            }
            fftwf_execute(target->forward);
            memcpy(target->filters+((size_t)s*nf+f)*fft_length,target->spectrum,
                fft_length*sizeof(fftwf_complex));
        }
    }
    target->used=++cache_clock;
    *built=ns*nf;
    return target;
error:
    destroy_kernel_entry(target);
    return NULL;
}
