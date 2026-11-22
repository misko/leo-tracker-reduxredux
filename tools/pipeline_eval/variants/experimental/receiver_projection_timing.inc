/* Lane-local two-frame ambiguity bank. This pilot aperture spans four symbols. */
enum { projection_frames = 2, projection_width = 44, projection_bands = 33 };
static const double projection_step = 50000.;

static int prepare_projection(TimingFirst *w) {
    if (w->stride != 4) return 1;
    w->linear_filters = reserve(w, projection_bands * bins, sizeof(Sample));
    w->linear_input = reserve(w, projection_frames * bins, sizeof(Sample));
    w->linear_low = reserve(w, points / 4, sizeof(Sample));
    if (!w->linear_filters || !w->linear_input || !w->linear_low) return 0;
    for (int branch = 0; branch < projection_bands; ++branch) {
        memset(w->scratch, 0, bins * sizeof(Sample));
        double freq = (branch - projection_bands / 2) * projection_step;
        for (int j = 0; j < projection_width; ++j) {
            double angle = turn * freq * j / w->rate;
            w->scratch[j] = multiply(w->code[j], (Sample){(float)cos(angle), (float)sin(angle)});
        }
        transform(w, bins, 0);
        for (int j = 0; j < bins; ++j)
            w->linear_filters[branch * bins + j] = conjugate(w->scratch[j]);
    }
    return 1;
}

static void cancellation_input(TimingFirst *w, const int16_t *original, const int16_t *residual,
                               int lane, double center) {
    double angle = -turn * center / 1e7, dr = cos(angle), di = sin(angle), ar = 1., ai = 0.;
    for (int i = 0; i < points; ++i) {
        int j = 4 * i + 2 * lane;
        Sample z = {(float)(original[j] - residual[j]), (float)(original[j + 1] - residual[j + 1])};
        if (center) {
            z = multiply(z, (Sample){(float)ar, (float)ai});
            double next = ar * dr - ai * di;
            ai = ar * di + ai * dr;
            ar = next;
        }
        w->data[i] = z;
    }
}

static void linear_times(TimingFirst *w, int residual, int *epochs) {
    int width = w->epochs + projection_width - 1;
    Sample spectra[projection_frames][bins];
    int starts[projection_frames] = {first / 4, rounded_offset(7, 4) + first / 4};
    for (int f = 0; f < projection_frames; ++f) {
        Sample *cache = w->linear_input + f * bins;
        memcpy(w->scratch, w->low + starts[f], width * sizeof(Sample));
        memset(w->scratch + width, 0, (bins - width) * sizeof(Sample));
        transform(w, bins, 0);
        if (residual) {
            for (int k = 0; k < bins; ++k)
                spectra[f][k] = (Sample){cache[k].re - w->scratch[k].re, cache[k].im - w->scratch[k].im};
        } else {
            memcpy(cache, w->scratch, bins * sizeof(Sample));
            memcpy(spectra[f], cache, bins * sizeof(Sample));
        }
    }
    if (residual) {
        for (int k = 0; k < points / 4; ++k)
            w->low[k] = (Sample){w->linear_low[k].re - w->low[k].re, w->linear_low[k].im - w->low[k].im};
    } else {
        memcpy(w->linear_low, w->low, (points / 4) * sizeof(Sample));
    }
    double inverse_energy[projection_frames][3333];
    for (int f = 0; f < projection_frames; ++f) {
        memcpy(w->modes + f * w->width, w->low + starts[f], w->width * sizeof(Sample));
        const Sample *block = w->low + starts[f];
        w->prefix[0] = 0.;
        for (int k = 0; k < width; ++k) w->prefix[k + 1] = w->prefix[k] + power(block[k]);
        for (int k = 0; k < w->epochs; ++k)
            inverse_energy[f][k] = 1. / fmax(w->prefix[k + projection_width] - w->prefix[k], 1e-15);
    }
    memset(w->time_score, 0, w->epochs * sizeof(double));
    for (int branch = 0; branch < projection_bands; ++branch) {
        const Sample *filter = w->linear_filters + branch * bins;
        memset(w->power, 0, w->epochs * sizeof(double));
        for (int f = 0; f < projection_frames; ++f) {
            for (int k = 0; k < bins; ++k)
                w->scratch[k] = conjugate(multiply(spectra[f][k], filter[k]));
            /* The forward plan on a conjugated spectrum gives inverse magnitudes.
               Its constant unnormalized scale is common to every hypothesis. */
            transform(w, bins, 0);
            for (int k = 0; k < w->epochs; ++k)
                w->power[k] += power(w->scratch[k]) * inverse_energy[f][k];
        }
        for (int k = 0; k < w->epochs; ++k)
            if (w->power[k] > w->time_score[k]) w->time_score[k] = w->power[k];
    }
    int radius = (int)nearbyint(6. / w->stride);
    for (int i = 0; i < clocks; ++i) {
        int best = 0;
        for (int k = 1; k < w->epochs; ++k)
            if (w->time_score[k] > w->time_score[best]) best = k;
        epochs[i] = best;
        for (int k = -radius; k <= radius; ++k)
            w->time_score[(best + k + w->epochs) % w->epochs] = -1.;
    }
}

int projection_detect(TimingFirst *w, const int16_t *actual, const int16_t *original, int lane,
                      double lo, double hi, TimingFirstResult *out, ProjectionTrace *trace) {
    if (!w || !actual || !out || !trace || lane < 0 || lane > 1 || !(lo < hi) ||
        lo < -5e6 || hi > 5e6 || w->stride != 4 || hi - lo > 1600000.) return -1;
    *out = (TimingFirstResult){0};
    trace->attempted = 1;
    unsigned nonzero = 0;
    for (int k = 0; k < points; ++k) {
        int j = 4 * k + 2 * lane;
        nonzero |= (unsigned)(actual[j] | actual[j + 1]);
    }
    trace->zero = !nonzero;
    if (trace->zero) return 0;

    double center = (lo + hi) / 2.;
    if (original) cancellation_input(w, original, actual, lane, center);
    else input(w, actual, lane, center);
    if (delay_decimate((float *)w->data, w->fir, 81, 4, (float *)w->low)) return -1;
    int epochs[clocks];
    linear_times(w, original != NULL, epochs);
    Seed seeds[2 * clocks];
    int n = find_carriers(w, epochs, lo, hi, center, seeds);
    Peak candidates[projection_seeds];
    if (original || center) input(w, actual, lane, 0.);
    for (int k = 0; k < projection_seeds && k < n; ++k) {
        int pick = 0;
        for (int j = 1; j < n; ++j)
            if (seeds[j].power > seeds[pick].power) pick = j;
        Seed seed = seeds[pick];
        seeds[pick].power = -1.;
        double hz = bin_hz(w, seed.bin) + center;
        if (hz < lo || hz > hi) continue;
        double v[4];
        if (delay_refine((float *)w->data, (float *)(w->pilot + first), seed.epoch, hz, lo, hi, v)) return -1;
        unsigned index = trace->seed_count++;
        trace->seeds[index] = (ProjectedSeed){v[0], v[1]};
        candidates[index] = (Peak){v[0], v[1], v[3], (int)v[2]};
    }
    for (unsigned k = 0; k < trace->seed_count; ++k) {
        unsigned best = 0;
        for (unsigned j = 1; j < trace->seed_count; ++j)
            if (candidates[j].score > candidates[best].score) best = j;
        Peak p = candidates[best];
        candidates[best].score = -1.;
        int why = 0;
        if (gate(w, &p, 160, 0) || gate(w, &p, 232, 0)) why = 1;
        else if (gate(w, &p, 0, 1)) why = 2;
        if (why) {
            *out = (TimingFirstResult){p.epoch, p.hz, p.score, why};
            break;
        }
    }
    return 0;
}
