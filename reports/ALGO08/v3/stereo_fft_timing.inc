/* Appended after the original timing receiver and extracted stock ranking helpers. */
typedef struct StereoTiming {
    fftwf_complex *buffer;
    fftwf_plan plan[fft_plans];
    int length;
} StereoTiming;

void stereo_timing_free(StereoTiming *p) {
    if (!p) return;
    pthread_mutex_lock(&planner_lock);
    for (int i = 0; i < fft_plans; ++i)
        if (p->plan[i]) fftwf_destroy_plan(p->plan[i]);
    pthread_mutex_unlock(&planner_lock);
    fftwf_free(p->buffer);
    free(p);
}

StereoTiming *stereo_timing_create(void) {
    StereoTiming *p = calloc(1, sizeof(*p));
    if (!p) return NULL;
    p->length = 4800;
    p->buffer = fftwf_alloc_complex(2 * p->length);
    if (!p->buffer) {
        stereo_timing_free(p);
        return NULL;
    }
    pthread_mutex_lock(&planner_lock);
    for (int i = 0; i < fft_plans; ++i) {
        int n = i == carrier_forward ? bins : p->length;
        int sign = i == timing_backward ? FFTW_BACKWARD : FFTW_FORWARD;
        p->plan[i] = fftwf_plan_many_dft(1, &n, 2, p->buffer, NULL, 1, p->length,
                                        p->buffer, NULL, 1, p->length, sign, FFTW_ESTIMATE);
    }
    pthread_mutex_unlock(&planner_lock);
    if (!p->plan[0] || !p->plan[1] || !p->plan[2]) {
        stereo_timing_free(p);
        return NULL;
    }
    return p;
}

size_t stereo_timing_bytes(const StereoTiming *p) {
    return sizeof(*p) + 2 * p->length * sizeof(fftwf_complex);
}

int stereo_timing_probe(StereoTiming *p, TimingFirst *left, TimingFirst *right,
                        int plan, const float *input, float *output) {
    if (plan < 0 || plan >= fft_plans) return -1;
    int n = plan == carrier_forward ? bins : p->length;
    TimingFirst *w[] = {left, right};
    for (int j = 0; j < 2; ++j) {
        memcpy(w[j]->scratch, input + 2 * n * j, n * sizeof(Sample));
        memcpy(p->buffer + p->length * j, input + 2 * n * j, n * sizeof(Sample));
        fftwf_execute(w[j]->plans[plan]);
        memcpy(output + 2 * n * j, w[j]->scratch, n * sizeof(Sample));
    }
    fftwf_execute(p->plan[plan]);
    for (int j = 0; j < 2; ++j)
        memcpy(output + 2 * n * (2 + j), p->buffer + p->length * j, n * sizeof(Sample));
    return 0;
}

static void stereo_times(StereoTiming *p, TimingFirst *w[2], int epochs[2][clocks]) {
    for (int j = 0; j < 2; ++j)
        memset(w[j]->time_score, 0, w[j]->epochs * sizeof(double));
    for (int k = 0; k < lags; ++k) {
        int lag = displacement(w[0], k), len = w[0]->length - lag;
        for (int j = 0; j < 2; ++j)
            spectral_lag_products(w[j]->scratch, w[j]->prefix, w[j]->modes, w[j]->modes + w[j]->width,
                                  w[j]->width, lag, p->length);
        fftwf_execute(p->plan[timing_forward]);
        for (int j = 0; j < 2; ++j)
            spectral_filter(w[j]->scratch, w[j]->filters + k * p->length, p->length);
        fftwf_execute(p->plan[timing_backward]);
        for (int j = 0; j < 2; ++j)
            spectral_timing_scores(w[j]->time_score, w[j]->prefix, w[j]->scratch,
                                   w[j]->epochs, len, p->length);
    }
    for (int j = 0; j < 2; ++j)
        stereo_rank_times(w[j], epochs[j]);
}

static int stereo_carriers(StereoTiming *p, TimingFirst *w[2], int epochs[2][clocks],
                           double lo, double hi, double center, Seed seeds[2][2 * clocks], int used[2]) {
    for (int j = 0; j < 2; ++j)
        if (experimental_carrier_eligibility_update(&w[j]->carrier_eligibility, w[j]->rate, lo, hi, center) < 0)
            return -1;
    int minimum_gap = (int)ceil(10000. * bins / w[0]->rate);
    int len = 64 * symbol / w[0]->stride;
    for (int i = 0; i < clocks; ++i) {
        double energy[2] = {0., 0.};
        for (int j = 0; j < 2; ++j)
            memset(w[j]->power, 0, bins * sizeof(double));
        for (int mode = 0; mode < 2; ++mode) {
            for (int j = 0; j < 2; ++j) {
                const Sample *v = w[j]->modes + mode * w[j]->width + epochs[j][i];
                energy[j] = spectral_carrier_input(w[j]->scratch, v, w[j]->code, len, bins, energy[j]);
            }
            fftwf_execute(p->plan[carrier_forward]);
            for (int j = 0; j < 2; ++j)
                spectral_carrier_power(w[j]->power, w[j]->scratch, bins);
        }
        for (int j = 0; j < 2; ++j) {
            CarrierEligibility *eligible = &w[j]->carrier_eligibility;
            used[j] = stereo_rank_carriers(w[j], epochs[j][i], eligible->eligible, eligible->count,
                                           minimum_gap, energy[j], seeds[j], used[j]);
        }
    }
    return 0;
}

int stereo_cancel_lane(TimingFirst *w, const float *pilot, float *scratch,
                       const TimingFirstResult *primary) {
    return pilot_cancel_resident((float *)w->data, pilot, scratch, primary->epoch, primary->hz);
}

int stereo_timing_detect(StereoTiming *p, TimingFirst *left, TimingFirst *right,
                         const int16_t *a, const int16_t *b, double lo, double hi, int resident,
                         TimingFirstResult out[2]) {
    if (!__builtin_cpu_supports("avx2") || !(lo < hi) || lo < -5e6 || hi > 5e6 || hi-lo > 1600000.)
        return -1;
    const int16_t *wave[2] = {a,b};
    TimingFirst *w[2] = {left,right};
    double center = (lo + hi) / 2.;
    if ((resident && center) || (!resident && (!a || !b))) return -1;
    for (int j = 0; j < 2; ++j) {
        out[j] = (TimingFirstResult){0};
        if (!resident) input(w[j], wave[j], j, center);
        if (delay_decimate((float *)w[j]->data, w[j]->fir, 81, 4, (float *)w[j]->low))
            return -1;
        principal_modes(w[j], w[j]->low);
    }
    Sample *scalar[2] = {left->scratch, right->scratch};
    left->scratch = (Sample *)p->buffer;
    right->scratch = (Sample *)(p->buffer + p->length);
    int epochs[2][clocks], used[2] = {0, 0};
    Seed seeds[2][2 * clocks];
    stereo_times(p, w, epochs);
    int status = stereo_carriers(p, w, epochs, lo, hi, center, seeds, used);
    left->scratch = scalar[0];
    right->scratch = scalar[1];
    if (status) return status;
    for (int j = 0; j < 2; ++j)
        if (stereo_finish_search(w[j], wave[j], j, lo, hi, center, out+j, seeds[j], used[j])) return -1;
    return 0;
}
