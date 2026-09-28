/* Experimental lag-product proposals. The FFT selects up to eight neighborhoods;
 * native-rate differential + signed-power correlation ranks their local cells.
 * No reference epoch/CFO, cached carrier phase, or previous visit is supplied. */
static double diff_projection(leo_presence_workspace *w, const double complex *values)
{
    size_t bins=w->power_fft.size;
    double complex mean=0;
    for (size_t k=0; k<bins; ++k) {
        double position=(double)k*w->n/bins;
        size_t left=(size_t)position, right=left+1;
        if (right==w->n) right=0;
        w->power_input[k]=values[left]+(position-left)*(values[right]-values[left]);
        mean+=w->power_input[k];
    }
    mean/=bins;
    double energy=0;
    for (size_t k=0; k<bins; ++k) {
        w->power_input[k]-=mean;
        energy+=power(w->power_input[k]);
    }
    return energy;
}

static void coarse_differential_template(leo_presence_workspace *w)
{
    double mean=0;
    double complex diff_mean=0;
    for (size_t k=0; k<w->n; ++k) {
        size_t next=(k+LEO_PRESENCE_DIFFERENTIAL_LAG)%w->n;
        w->diff_template[k]=w->exact[next]*conj(w->exact[k]);
        w->power_native_template[k]=power(w->exact[k]);
        mean+=w->power_native_template[k]; diff_mean+=w->diff_template[k];
    }
    mean/=w->n; diff_mean/=w->n;
    for (size_t k=0; k<w->n; ++k) {
        w->power_native_template[k]-=mean;
        w->diff_template[k]-=diff_mean;
        w->power_native_template_energy+=w->power_native_template[k]*w->power_native_template[k];
        w->diff_template_energy+=power(w->diff_template[k]);
    }
    w->power_template_energy=diff_projection(w,w->diff_template);
    leo_fft_forward(&w->power_fft,w->power_input);
    memcpy(w->power_template_fft,w->power_fft.output,w->power_fft.size*sizeof(double complex));
}

static double diff_native_cell(leo_presence_workspace *w, size_t epoch,
    double power_norm, double diff_norm)
{
    double p=0;
    double complex d=0;
    size_t split=w->n-epoch;
    for (size_t k=0; k<split; ++k) {
        p+=w->power_native_folded[k+epoch]*w->power_native_template[k];
        d+=w->diff_folded[k+epoch]*conj(w->diff_template[k]);
    }
    for (size_t k=split; k<w->n; ++k) {
        p+=w->power_native_folded[k-split]*w->power_native_template[k];
        d+=w->diff_folded[k-split]*conj(w->diff_template[k]);
    }
    return (diff_norm>0 ? magnitude(d)/diff_norm : 0) +
        (power_norm>0 ? (LEO_PRESENCE_DIFFERENTIAL_POWER_MILLI/1000.0)*p/power_norm : 0);
}

#if LEO_PRESENCE_DIFFERENTIAL_CI16
#include "ci16_fold.h"
#endif

static int coarse_differential(leo_presence_workspace *w, size_t count, const int16_t *iq)
{
    (void)iq;
#if LEO_PRESENCE_DIFFERENTIAL_CI16
    if (iq) coarse_fold_ci16(w,iq,count);
    else {
#endif
    memset(w->power_native_folded,0,w->n*sizeof(double));
    memset(w->diff_folded,0,w->n*sizeof(double complex));
    memset(w->support,0,w->n*sizeof(int32_t));
    memset(w->diff_support,0,w->n*sizeof(int32_t));
    for (int frame=0; frame<16; ++frame) {
        size_t start=(size_t)frame_start(w,0,frame);
        if (start>=count) break;
        size_t valid=count-start;
        if (valid>w->n) valid=w->n;
        for (size_t k=0; k<valid; ++k) {
            w->power_native_folded[k]+=power(w->samples[start+k]);
            ++w->support[k];
            if (start+k+LEO_PRESENCE_DIFFERENTIAL_LAG<count) {
                w->diff_folded[k]+=w->samples[start+k+LEO_PRESENCE_DIFFERENTIAL_LAG]*conj(w->samples[start+k]);
                ++w->diff_support[k];
            }
        }
    }
#if LEO_PRESENCE_DIFFERENTIAL_CI16
    }
#endif
    double mean=0;
    double complex diff_mean=0;
    for (size_t k=0; k<w->n; ++k) {
        w->power_native_folded[k]/=w->support[k]>0 ? w->support[k] : 1;
        w->diff_folded[k]/=w->diff_support[k]>0 ? w->diff_support[k] : 1;
        mean+=w->power_native_folded[k]; diff_mean+=w->diff_folded[k];
    }
    mean/=w->n; diff_mean/=w->n;
    w->power_native_folded_energy=0; w->diff_folded_energy=0;
    for (size_t k=0; k<w->n; ++k) {
        w->power_native_folded[k]-=mean; w->diff_folded[k]-=diff_mean;
        w->power_native_folded_energy+=w->power_native_folded[k]*w->power_native_folded[k];
        w->diff_folded_energy+=power(w->diff_folded[k]);
    }
    double energy=diff_projection(w,w->diff_folded);
    double norm=sqrt(energy*w->power_template_energy);
    for (size_t k=0; k<CFO_COUNT*w->n; ++k) w->grid[k]=-INFINITY;
    if (norm==0) { memset(w->grid+5*w->n,0,w->n*sizeof(double)); return 0; }
    leo_fft_forward(&w->power_fft,w->power_input);
    for (size_t k=0; k<w->power_fft.size; ++k)
        w->power_input[k]=conj(w->power_fft.output[k]*conj(w->power_template_fft[k]));
    leo_fft_forward(&w->power_fft,w->power_input);
    double *scores=w->grid+5*w->n;
    for (size_t k=0; k<w->n; ++k) {
        double position=(double)k*w->power_fft.size/w->n;
        size_t left=(size_t)position, right=left+1;
        if (right==w->power_fft.size) right=0;
        double complex value=w->power_fft.output[left];
        value+=(position-left)*(w->power_fft.output[right]-value);
        scores[k]=magnitude(value)/(w->power_fft.size*norm);
    }
    int epochs[8], selected=0;
    for (int selection=0; selection<8; ++selection) {
        int best=-1;
        for (int k=0; k<(int)w->n; ++k) {
            int left=k ? k-1 : (int)w->n-1, right=k+1==(int)w->n ? 0 : k+1;
            if (!(scores[k]>=scores[left] && scores[k]>=scores[right] &&
                (scores[k]>scores[left] || scores[k]>scores[right]))) continue;
            int near=0;
            for (int j=0; j<selected; ++j) {
                int distance=abs(k-epochs[j]);
                if (distance>(int)w->n-distance) distance=(int)w->n-distance;
                if (distance<5) near=1;
            }
            if (!near && (best<0 || scores[k]>scores[best])) best=k;
        }
        if (best<0 || scores[best]<=0) break;
        epochs[selected++]=best;
    }
    for (size_t k=0; k<w->n; ++k) scores[k]=-INFINITY;
    double power_norm=sqrt(w->power_native_template_energy*w->power_native_folded_energy);
    double diff_norm=sqrt(w->diff_template_energy*w->diff_folded_energy);
    /* Projection is upsampling only, so one native sample on either side
     * covers its local quantization uncertainty. All other cells stay absent. */
    for (int j=0; j<selected; ++j)
        for (int delta=-LEO_PRESENCE_DIFFERENTIAL_LOCAL_RADIUS;
            delta<=LEO_PRESENCE_DIFFERENTIAL_LOCAL_RADIUS; ++delta) {
        int epoch=(epochs[j]+delta+(int)w->n)%(int)w->n;
        scores[epoch]=diff_native_cell(w,(size_t)epoch,power_norm,diff_norm);
    }
    return 0;
}
