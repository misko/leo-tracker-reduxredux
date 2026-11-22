static _Thread_local ShortlistAudit *shortlist;
typedef struct {
    int used;
    Peak peaks[max_peaks];
    SecondSeed seeds[max_peaks];
} ChoiceTrace;
static _Thread_local ChoiceTrace *choices_trace;

static void record_first_choice(Peak peak, int epoch, double hz) {
    if (!choices_trace) return;
    int i = choices_trace->used++;
    choices_trace->peaks[i] = peak;
    choices_trace->seeds[i] = (SecondSeed){epoch, hz, {peak.epoch, peak.hz, peak.score, 0}};
}

static int same_proposal(double e, double f, const TimingFirstResult *other) {
    return fabs(remainder(e - other->epoch, period)) <= 2. && fabs(f - other->hz) <= 1000.;
}

static int confirm_peak(TimingFirst *w, const Peak *peak) {
    if (gate(w, peak, 160, 0) || gate(w, peak, 232, 0)) return 1;
    return gate(w, peak, 0, 1) ? 2 : 0;
}

int timing_shortlist_pair(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,
                          TimingFirstResult *first_peak, SecondSeed *second, int *used) {
    if (choices_trace) return -1;
    ChoiceTrace trace = {0};
    choices_trace = &trace;
    int status = timing_first_detect(w, iq, lane, lo, hi, first_peak);
    choices_trace = NULL;
    *used = 0;
    if (status || !first_peak->confirmation) return status;
    for (int i = 0; i < trace.used; ++i) {
        const Peak *peak = &trace.peaks[i];
        if (same_proposal(peak->epoch, peak->hz, first_peak) ||
            (*used && same_proposal(peak->epoch, peak->hz, &second->raw))) continue;
        if (!confirm_peak(w, peak)) continue;
        if (*used) {
            *used = 0; /* Multiple plausible alternatives need a complete residual search. */
            return 0;
        }
        *second = trace.seeds[i];
        *used = 1;
    }
    return 0;
}

int timing_shortlist_residual(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,
                              SecondSeed seed, TimingFirstResult *out) {
    *out = (TimingFirstResult){0};
    input(w, iq, lane, 0.);
    double value[4];
    if (delay_refine((float *)w->data, (float *)(w->pilot + first), seed.epoch, seed.hz, lo, hi, value))
        return -1;
    if (!same_proposal(value[0], value[1], &seed.raw) || fabs(value[1] - seed.raw.hz) > 250.) return 0;
    Peak peak = {value[0], value[1], value[3], (int)value[2]};
    int confirmed = confirm_peak(w, &peak);
    if (confirmed) *out = (TimingFirstResult){peak.epoch, peak.hz, peak.score, confirmed};
    return 0;
}

static int target_epoch(double epoch) {
    return fabs(remainder(epoch - shortlist->epoch, period)) <= 7.;
}

static int target_hz(double hz) {
    return fabs(hz - shortlist->hz) <= 1000. + 1e7 / (64. * symbol);
}

static void audit_timing_grid(const TimingFirst *w) {
    if (!shortlist) return;
    double target = -INFINITY;
    int best = -1;
    for (int i = 0; i < w->epochs; ++i)
        if (target_epoch(i * w->stride) && w->time_score[i] > target) {
            target = w->time_score[i];
            best = i;
        }
    if (best < 0) return;
    int rank = 1;
    for (int i = 0; i < w->epochs; ++i)
        rank += w->time_score[i] > target || (w->time_score[i] == target && i < best);
    shortlist->timing_cell_rank = rank;
}

static void audit_carrier_grid(const TimingFirst *w, int epoch, int timing_rank, const uint16_t *eligible,
                               int count, double lo, double hi, double center) {
    if (!shortlist || !target_epoch(epoch)) return;
    if (!shortlist->timing_seed_rank) shortlist->timing_seed_rank = timing_rank;
    double value = -INFINITY;
    int best = -1;
    for (int i = 0; i < count; ++i) {
        int bin = eligible[i];
        double base = bin_hz(w, bin) + center;
        double absolute = base + w->rate * nearbyint((shortlist->hz - base) / w->rate);
        if (absolute >= lo && absolute <= hi && target_hz(absolute) && w->power[bin] > value) {
            value = w->power[bin];
            best = i;
        }
    }
    if (best < 0) return;
    int rank = 1;
    for (int i = 0; i < count; ++i) {
        double score = w->power[eligible[i]];
        rank += score > value || (score == value && i < best);
    }
    if (!shortlist->frequency_cell_rank || rank < shortlist->frequency_cell_rank)
        shortlist->frequency_cell_rank = rank;
}

static int audit_before_pruning(TimingFirst *w, const Seed *source, int count, double lo, double hi,
                                double center) {
    if (!shortlist) return 0;
    shortlist->seeds_used = count;
    Seed seeds[audit_seeds];
    if (count > audit_seeds) return -1;
    memcpy(seeds, source, count * sizeof(*seeds));
    for (int rank = 1; rank <= count; ++rank) {
        int best = 0;
        for (int i = 1; i < count; ++i)
            if (seeds[i].power > seeds[best].power) best = i;
        Seed seed = seeds[best];
        seeds[best].power = -1.;
        if (!target_epoch(seed.epoch)) continue;
        double hz = bin_hz(w, seed.bin) + center;
        hz += w->rate * nearbyint((shortlist->hz - hz) / w->rate);
        if (!target_hz(hz) || hz < lo || hz > hi) continue;
        if (!shortlist->coarse_rank) shortlist->coarse_rank = rank;
        double v[4];
        if (delay_refine((float *)w->data, (float *)(w->pilot + first), seed.epoch, hz, lo, hi, v))
            return -1;
        if (fabs(remainder(v[0] - shortlist->epoch, period)) > 2. || fabs(v[1] - shortlist->hz) > 1000.)
            continue;
        if (!shortlist->refined_rank) shortlist->refined_rank = rank;
        Peak p = {v[0], v[1], v[3], (int)v[2]};
        int confirmed = gate(w, &p, 160, 0) || gate(w, &p, 232, 0) || gate(w, &p, 0, 1);
        if (confirmed && !shortlist->confirmed_rank) shortlist->confirmed_rank = rank;
        shortlist->peaks[shortlist->candidates++] = (AuditPeak){p.epoch, p.hz, rank, confirmed};
    }
    return 0;
}

int timing_shortlist_audit(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,
                           ShortlistAudit *result) {
    if (!result || shortlist) return -1;
    shortlist = result;
    TimingFirstResult timing;
    int status = timing_first_detect(w, iq, lane, lo, hi, &timing);
    shortlist = NULL;
    if (!status) result->first_confirmed = timing.confirmation != 0;
    return status;
}
