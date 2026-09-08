/* One bounded stationary-tone nuisance fit. This changes the experimental
 * working signal, not the original IQ, and is always separately identified. */
#if LEO_PRESENCE_TONE_CI16
#include "ci16_lag.h"
#endif
static int tone_nuisance(leo_presence_workspace *w, size_t count, const int16_t *iq)
{
    (void)iq;
    if (count!=w->max_samples) return -1;
    double energy=0;
#if LEO_PRESENCE_TONE_CI16
    if (iq) energy=creal(ci16_lag_sum(iq,count,0));
    else
#endif
        for (size_t k=0; k<count; ++k) energy+=power(w->samples[k]);
    if (energy==0) return 0;
    size_t size=w->power_fft.size, peak=0;
    leo_fft_forward(&w->power_fft,w->samples);
    double spectrum_energy=0, peak_power=-1;
    for (size_t k=0; k<size; ++k) {
        double value=power(w->power_fft.output[k]);
        spectrum_energy+=value;
        if (value>peak_power) { peak_power=value; peak=k; }
    }
    if (spectrum_energy==0) return 0;
    size_t left=peak ? peak-1 : size-1, right=peak+1==size ? 0 : peak+1;
    double fraction=(peak_power+power(w->power_fft.output[left])+power(w->power_fft.output[right]))/spectrum_energy;
    w->nuisance.spectral_fraction=fraction;
    if (fraction<0.02) return 0;
    int signed_bin=peak<size/2 ? (int)peak : (int)peak-(int)size;
    double frequency=(double)signed_bin*w->rate/size;
    const size_t lags[3]={256,4096,16384};
    for (int j=0; j<3; ++j) {
        size_t lag=lags[j];
        double complex product=0;
#if LEO_PRESENCE_TONE_CI16
        if (iq) product=ci16_lag_sum(iq,count,lag);
        else {
#endif
#if LEO_PRESENCE_TONE_BLOCKED
        double complex p0=0,p1=0,p2=0,p3=0;
        size_t k=0;
        for (; k+3<count-lag; k+=4) {
            p0+=conj(w->samples[k])*w->samples[k+lag];
            p1+=conj(w->samples[k+1])*w->samples[k+lag+1];
            p2+=conj(w->samples[k+2])*w->samples[k+lag+2];
            p3+=conj(w->samples[k+3])*w->samples[k+lag+3];
        }
        product=(p0+p1)+(p2+p3);
        for (; k<count-lag; ++k) product+=conj(w->samples[k])*w->samples[k+lag];
#else
        for (size_t k=0; k<count-lag; ++k)
            product+=conj(w->samples[k])*w->samples[k+lag];
#endif
#if LEO_PRESENCE_TONE_CI16
        }
#endif
        if (cabs(product)<=DBL_MIN) return 0;
        double period=(double)w->rate/lag;
        double local=atan2(cimag(product),creal(product))*period/TAU;
        frequency=local+nearbyint((frequency-local)/period)*period;
    }
    w->nuisance.frequency_hz=frequency;
    double complex step=rotate(TAU*frequency/w->rate), oscillator=1, amplitude=0;
#if LEO_PRESENCE_TONE_BLOCKED
    /* Factor each 256-sample oscillator block into a reusable local basis and
     * one block rotation. This evaluates the same whole-probe LS model, with
     * no per-sample oscillator recurrence and no loss of temporal support. */
    double complex basis[256];
    for (size_t j=0; j<256; ++j) { basis[j]=oscillator; oscillator*=step; }
    for (size_t start=0; start<count; start+=256) {
        size_t end=count-start<256 ? count-start : 256, j=0;
        double complex a0=0,a1=0,a2=0,a3=0;
        for (; j+3<end; j+=4) {
            a0+=conj(basis[j])*w->samples[start+j];
            a1+=conj(basis[j+1])*w->samples[start+j+1];
            a2+=conj(basis[j+2])*w->samples[start+j+2];
            a3+=conj(basis[j+3])*w->samples[start+j+3];
        }
        double complex local=(a0+a1)+(a2+a3);
        for (; j<end; ++j) local+=conj(basis[j])*w->samples[start+j];
        amplitude+=conj(rotate(TAU*frequency*start/w->rate))*local;
    }
#else
    for (size_t k=0; k<count; ++k) {
        amplitude+=conj(oscillator)*w->samples[k];
        oscillator*=step;
        /* Re-anchor the recurrence so long probes cannot accumulate phase or
         * amplitude drift. No absolute device counter enters this arithmetic. */
        if ((k&255)==255) oscillator=rotate(TAU*frequency*(k+1)/w->rate);
    }
#endif
    amplitude/=count;
    double fitted=power(amplitude)*count/energy;
    w->nuisance.fitted_power_fraction=fitted;
    if (fitted<0.01) return 0;
#if LEO_PRESENCE_TONE_BLOCKED
    for (size_t start=0; start<count; start+=256) {
        size_t end=count-start<256 ? count-start : 256;
        double complex local=amplitude*rotate(TAU*frequency*start/w->rate);
        for (size_t j=0; j<end; ++j) w->samples[start+j]-=local*basis[j];
    }
#else
    oscillator=1;
    for (size_t k=0; k<count; ++k) {
        w->samples[k]-=amplitude*oscillator;
        oscillator*=step;
        if ((k&255)==255) oscillator=rotate(TAU*frequency*(k+1)/w->rate);
    }
#endif
    w->nuisance.applied=1;
    return 0;
}
