/* For Y = FFT(lag products) times the frozen pilot filter, the even
   inverse-DFT outputs are the half-size inverse of Y[k] + Y[k + N/2].
   The odd outputs use (Y[k] - Y[k + N/2]) times exp(2 pi i k / N). */
static int prepare_polyphase(TimingFirst *w) {
    if (w->stride != 4)
        return 1;
    int half = w->correlation_size / 2;
#if timing_fold_both
    w->odd_rotation = reserve(w, half, sizeof(Sample));
    if (!w->odd_rotation)
        return 0;
    for (int k = 0; k < half; ++k) {
        double angle = turn * k / w->correlation_size;
        w->odd_rotation[k] = (Sample){(float)cos(angle), (float)sin(angle)};
    }
#endif
    fftwf_complex *scratch = (fftwf_complex *)w->scratch;
    pthread_mutex_lock(&planner_lock);
    w->folded_inverse = fftwf_plan_dft_1d(half, scratch, scratch, FFTW_BACKWARD, FFTW_ESTIMATE);
    pthread_mutex_unlock(&planner_lock);
    return w->folded_inverse != NULL;
}

static void release_polyphase(TimingFirst *w) {
    pthread_mutex_lock(&planner_lock);
    if (w->folded_inverse)
        fftwf_destroy_plan(w->folded_inverse);
    pthread_mutex_unlock(&planner_lock);
    free(w->odd_rotation);
}

static void fold_polyphase(Sample *spectrum, const Sample *rotation, int half) {
    for (int k = 0; k < half; ++k) {
        Sample a = spectrum[k], b = spectrum[k + half];
        spectrum[k] = (Sample){a.re + b.re, a.im + b.im};
#if timing_fold_both
        spectrum[k + half] = multiply((Sample){a.re - b.re, a.im - b.im}, rotation[k]);
#endif
    }
}

static void polyphase_scores(TimingFirst *w, int length) {
    const int n = w->correlation_size, half = n / 2;
    const float scale = 1.f / n;
    fold_polyphase(w->scratch, w->odd_rotation, half);
    fftwf_execute(w->folded_inverse);
#if timing_fold_both
    /* The upper half starts 2,400 complex floats later at stride four,
       preserving the aligned new-array execution requirements of this plan. */
    fftwf_complex *odd = (fftwf_complex *)(w->scratch + half);
    fftwf_execute_dft(w->folded_inverse, odd, odd);
#endif
    const int step = timing_fold_both ? 1 : 2;
    for (int i = 0; i < w->epochs; i += step) {
        Sample z = w->scratch[i / 2 + (i % 2) * half];
        z = (Sample){z.re * scale, z.im * scale};
        w->time_score[i] += power(z) / fmax(w->prefix[i + length] - w->prefix[i], 1e-20);
    }
}

static void polyphase_select(TimingFirst *w, int *epochs) {
    const int step = timing_fold_both ? 1 : 2;
    const int radius = (int)nearbyint(6. / w->stride);
    for (int k = 0; k < clocks; ++k) {
        int best = 0;
        for (int i = step; i < w->epochs; i += step)
            if (w->time_score[i] > w->time_score[best])
                best = i;
        int refined = best;
#if !timing_fold_both
        /* Interpolate only while the two original neighbors are present.
           The caller still checks the complete signed carrier FFT at this epoch. */
        if (best >= step && best + step < w->epochs) {
            double left = w->time_score[best - step], peak = w->time_score[best];
            double right = w->time_score[best + step];
            double curvature = 2 * peak - left - right;
            if (left >= 0 && right >= 0 && curvature > 0) {
                double shift = (right - left) / curvature;
                if (shift > .5)
                    ++refined;
                if (shift < -.5)
                    --refined;
            }
        }
#endif
        epochs[k] = refined;
        for (int j = -radius; j <= radius; ++j)
            w->time_score[(refined + j + w->epochs) % w->epochs] = -1.;
    }
}

static void find_polyphase_times(TimingFirst *w, int *epochs) {
    memset(w->time_score, 0, w->epochs * sizeof(double));
    for (int k = 0; k < lags; ++k) {
        int lag = displacement(w, k);
        spectral_lag_products(w->scratch, w->prefix, w->modes, w->modes + w->width,
                              w->width, lag, w->correlation_size);
        transform(w, w->correlation_size, 0);
        spectral_filter(w->scratch, w->filters + k * w->correlation_size, w->correlation_size);
        polyphase_scores(w, w->length - lag);
    }
    polyphase_select(w, epochs);
}
