/* CFO-invariant pilot-power timing proposals. This is a different detector,
 * not the symbolwise GLRT coarse grid. Full-rate original IQ is retained for
 * subsequent blind CFO acquisition and fractional confirmation. */
static double power_projection(leo_presence_workspace *w, const double *values)
{
    size_t length=LEO_PRESENCE_POWER_BINS ? LEO_PRESENCE_POWER_BINS : w->n;
    memset(w->power_input,0,w->power_fft.size*sizeof(double complex));
    double mean=0, energy=0;
    for (size_t k=0; k<length; ++k) {
        double position=(double)k*w->n/length;
        size_t left=(size_t)position, right=left+1;
        if (right==w->n) right=0;
        double fraction=position-left;
        double value=values[left]+fraction*(values[right]-values[left]);
        w->power_input[k]=value;
        mean+=value;
    }
    /* The optional projection changes only the proposal phase grid, not the
     * physical frame offsets used to fold the original-rate samples. */
    mean=LEO_PRESENCE_POWER_BINS ? mean/length : 0;
    for (size_t k=0; k<length; ++k) {
        double value=creal(w->power_input[k])-mean;
        w->power_input[k]=value;
        energy+=value*value;
    }
    return energy;
}

static void coarse_power_template(leo_presence_workspace *w)
{
    double mean=0;
    for (size_t k=0; k<w->n; ++k) mean+=power(w->exact[k]);
    mean/=w->n;
    for (size_t k=0; k<w->n; ++k) {
        double value=power(w->exact[k])-mean;
        w->power_native_template[k]=value;
        w->power_native_template_energy+=value*value;
    }
    w->power_template_energy=power_projection(w,w->power_native_template);
    leo_fft_forward(&w->power_fft,w->power_input);
    memcpy(w->power_template_fft,w->power_fft.output,w->power_fft.size*sizeof(double complex));
}

static int coarse_power(leo_presence_workspace *w, size_t count)
{
    memset(w->power_native_folded,0,w->n*sizeof(double));
    memset(w->support,0,w->n*sizeof(int32_t));
    for (int frame=0; frame<16; ++frame) {
        size_t start=(size_t)frame_start(w,0,frame);
        if (start>=count) break;
        size_t valid=count-start;
        if (valid>w->n) valid=w->n;
        for (size_t k=0; k<valid; ++k) {
            w->power_native_folded[k]+=power(w->samples[start+k]);
            ++w->support[k];
        }
    }
    double mean=0;
    for (size_t k=0; k<w->n; ++k) {
        w->power_native_folded[k]/=w->support[k]>0 ? w->support[k] : 1;
        mean+=w->power_native_folded[k];
    }
    mean/=w->n;
    w->power_native_folded_energy=0;
    for (size_t k=0; k<w->n; ++k) {
        double value=w->power_native_folded[k]-mean;
        w->power_native_folded[k]=value;
        w->power_native_folded_energy+=value*value;
    }
    double energy=power_projection(w,w->power_native_folded);
    for (size_t k=0; k<CFO_COUNT*w->n; ++k) w->grid[k]=-INFINITY;
    double norm=sqrt(energy*w->power_template_energy);
    if (norm==0) {
        memset(w->grid+5*w->n,0,w->n*sizeof(double));
        return 0;
    }
    leo_fft_forward(&w->power_fft,w->power_input);
    /* Conjugated forward transform implements the real inverse correlation. */
    for (size_t k=0; k<w->power_fft.size; ++k)
        w->power_input[k]=conj(w->power_fft.output[k]*conj(w->power_template_fft[k]));
    leo_fft_forward(&w->power_fft,w->power_input);
    for (size_t epoch=0; epoch<w->n; ++epoch) {
#if LEO_PRESENCE_POWER_BINS
        double position=(double)epoch*LEO_PRESENCE_POWER_BINS/w->n;
        size_t left=(size_t)position, right=left+1;
        if (right==LEO_PRESENCE_POWER_BINS) right=0;
        double value=creal(w->power_fft.output[left]);
        value+=(position-left)*(creal(w->power_fft.output[right])-value);
#else
        double value=creal(w->power_fft.output[epoch]);
        if (epoch) value+=creal(w->power_fft.output[w->power_fft.size+epoch-w->n]);
#endif
        w->grid[5*w->n+epoch]=value/(w->power_fft.size*norm);
    }
    return 0;
}

#if LEO_PRESENCE_POWER_BINS
static void coarse_power_cell(leo_presence_workspace *w, int epoch)
{
    double value=0;
    size_t split=w->n-(size_t)epoch;
    /* Split the circular dot product instead of dividing once per sample. */
    for (size_t k=0; k<split; ++k)
        value+=w->power_native_folded[k+epoch]*w->power_native_template[k];
    for (size_t k=split; k<w->n; ++k)
        value+=w->power_native_folded[k-split]*w->power_native_template[k];
    double norm=sqrt(w->power_native_template_energy*w->power_native_folded_energy);
    w->grid[5*w->n+epoch]=norm>0 ? value/norm : 0;
}
#endif
