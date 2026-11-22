/* Included in the experimental timing translation unit after its workspace. */
#include <pthread.h>

enum { timing_forward, timing_backward, carrier_forward, fft_plans };
static pthread_mutex_t planner_lock = PTHREAD_MUTEX_INITIALIZER;

#ifndef CORRELATION_SIZE
#define CORRELATION_SIZE(w) ((w)->fft_size)
#endif

static int prepare_fft(TimingFirst *w) {
    fftwf_complex *z = (fftwf_complex *)w->scratch;
    pthread_mutex_lock(&planner_lock);
    w->plans[timing_forward] = fftwf_plan_dft_1d(CORRELATION_SIZE(w), z, z, FFTW_FORWARD, FFTW_ESTIMATE);
    w->plans[timing_backward] = fftwf_plan_dft_1d(CORRELATION_SIZE(w), z, z, FFTW_BACKWARD, FFTW_ESTIMATE);
    w->plans[carrier_forward] = fftwf_plan_dft_1d(bins, z, z, FFTW_FORWARD, FFTW_ESTIMATE);
    pthread_mutex_unlock(&planner_lock);
    return w->plans[timing_forward] && w->plans[timing_backward] && w->plans[carrier_forward];
}

static void release_fft(TimingFirst *w) {
    pthread_mutex_lock(&planner_lock);
    for (int i = 0; i < fft_plans; ++i)
        if (w->plans[i]) fftwf_destroy_plan(w->plans[i]);
    pthread_mutex_unlock(&planner_lock);
    fftwf_free(w->scratch);
}

static int transform_large(TimingFirst *w, int n, int backward) {
    if (n < bins) return 0;
    int plan = n == CORRELATION_SIZE(w) ? (backward ? timing_backward : timing_forward) : carrier_forward;
    fftwf_execute(w->plans[plan]);
    if (backward) {
        const float scale = 1.f / n;
        for (int i = 0; i < n; ++i) {
            w->scratch[i].re *= scale;
            w->scratch[i].im *= scale;
        }
    }
    return 1;
}
