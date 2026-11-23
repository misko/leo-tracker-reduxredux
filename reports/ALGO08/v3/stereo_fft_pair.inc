/* Appended after the original two-carrier entry; each lane keeps its own data. */
typedef struct StereoTiming StereoTiming;
StereoTiming *stereo_timing_create(void);
void stereo_timing_free(StereoTiming *);
size_t stereo_timing_bytes(const StereoTiming *);
int stereo_timing_probe(StereoTiming *, TimingFirst *, TimingFirst *, int, const float *, float *);
int stereo_cancel_lane(TimingFirst *, const float *, float *, const TimingFirstResult *);
int stereo_timing_detect(StereoTiming *, TimingFirst *, TimingFirst *, const int16_t *,
                         const int16_t *, double, double, int, TimingFirstResult[2]);

typedef struct {
    TwoCarrierReceiver *radio[2];
    StereoTiming *timing;
} StereoReceiver;

void stereo_receiver_free(StereoReceiver *p) {
    if (!p) return;
    two_carrier_free(p->radio[0]);
    two_carrier_free(p->radio[1]);
    stereo_timing_free(p->timing);
    free(p);
}

StereoReceiver *stereo_receiver_create(const float *asset, int paired) {
    StereoReceiver *p = calloc(1, sizeof(*p));
    if (!p) return NULL;
    p->radio[0] = two_carrier_create(asset);
    if (paired) {
        p->radio[1] = two_carrier_create(asset);
        p->timing = stereo_timing_create();
    }
    if (!p->radio[0] || (paired && (!p->radio[1] || !p->timing))) {
        stereo_receiver_free(p);
        return NULL;
    }
    return p;
}

size_t stereo_receiver_bytes(const StereoReceiver *p) {
    return sizeof(*p) + two_carrier_bytes(p->radio[0]) + two_carrier_bytes(p->radio[1])
        + (p->timing ? stereo_timing_bytes(p->timing) : 0);
}

int stereo_receiver_probe(StereoReceiver *p, int plan, const float *input, float *output) {
    return p->timing ? stereo_timing_probe(p->timing, p->radio[0]->timing, p->radio[1]->timing,
                                           plan, input, output) : -1;
}

static int stereo_single_residual(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                                  double lo, double hi, const TimingFirstResult *primary,
                                  TimingFirstResult *residual) {
    if ((lo + hi) / 2. == 0.)
        return timing_first_cancel_resident(r->timing, r->synthesis, r->rotated, primary, lo, hi, residual);
    return pilot_cancel(iq, r->residual, lane, r->synthesis, r->rotated, primary->epoch, primary->hz)
        || timing_first_detect(r->timing, r->residual, lane, lo, hi, residual);
}

int stereo_receiver_run(StereoReceiver *p, const int16_t *iq, double lo, double hi, unsigned mask,
                        ScanFactor out[2][2], int count[2], int paths[4]) {
    if (!p || !iq || mask < 1 || mask > 3) return -1;
    memset(paths, 0, 4 * sizeof(*paths));
    count[0] = count[1] = 0;
    if (!p->timing || mask != 3 || !__builtin_cpu_supports("avx2")) {
        paths[3] = mask != 3;
        for (int j = 0; j < 2; ++j)
            if (mask & (1u << j)) {
                count[j] = cancellation_factors(p->radio[0], iq, j, lo, hi, out[j]);
                if (count[j] < 0) return -1;
            }
        return 0;
    }
    TwoCarrierReceiver **r = p->radio;
    TimingFirstResult primary[2], residual[2] = {{0},{0}};
    if (stereo_timing_detect(p->timing, r[0]->timing, r[1]->timing, iq, iq, lo, hi, 0, primary))
        return -1;
    paths[0] = 1;
    if (primary[0].confirmation && primary[1].confirmation) {
        int resident = (lo + hi) / 2. == 0.;
        for (int j = 0; j < 2; ++j) {
            int status = resident ? stereo_cancel_lane(r[j]->timing, r[j]->synthesis, r[j]->rotated, primary+j)
                : pilot_cancel(iq, r[j]->residual, j, r[j]->synthesis, r[j]->rotated,
                               primary[j].epoch, primary[j].hz);
            if (status) return -1;
        }
        if (stereo_timing_detect(p->timing, r[0]->timing, r[1]->timing,
                                 r[0]->residual, r[1]->residual, lo, hi, resident, residual))
            return -1;
        paths[1] = 1;
    } else {
        for (int j = 0; j < 2; ++j)
            if (primary[j].confirmation) {
                if (stereo_single_residual(r[j], iq, j, lo, hi, primary+j, residual+j)) return -1;
                paths[2] = 1;
            }
    }
    for (int j = 0; j < 2; ++j)
        if (primary[j].confirmation) {
            TimingFirstResult input[2] = {primary[j], residual[j]};
            TwoCarrierPeak peaks[2];
            if (portable_verifier_load(r[j]->verify, iq, (unsigned)j)) return -1;
            count[j] = verify_peaks(r[j], input, peaks, out[j], 1);
            if (count[j] < 0) return -1;
        }
    return 0;
}
