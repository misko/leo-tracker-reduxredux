/* Included after the pinned v3 receiver definitions. This research readout does
   not publish the released GLRT score contract. */

typedef struct {
    unsigned examined, flags;
    double offset, residual_hz, exact, control;
} StockReadout;

typedef struct {
    int examined, accepted, rolled_accepted, frames;
    double offset, hz, exact, control, group_hz[2];
} BlockReadout;

typedef struct {
    TimingFirstResult scout[2];
    StockReadout stock[2];
    BlockReadout block[2];
    uint64_t loading_cpu_ns, verification_cpu_ns;
} ScoutReadoutTrace;

static _Thread_local ScoutReadoutTrace *readout_trace;

static void trace_stock_result(int rank, const PortableVerifierResult *v) {
    if (readout_trace)
        readout_trace->stock[rank] = (StockReadout){1, v->flags, v->offset_samples,
            v->fractional_residual_hz, v->fractional_exact, v->fractional_control};
}

static uint64_t readout_cpu(void) {
    struct timespec t;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + t.tv_nsec;
}

enum { held_start = 88 + 130*44, block_size = 7*44, held_blocks = 4, held_size = block_size*held_blocks };
static const double readout_tau = 6.283185307179586476925286766559;
static const double readout_rate = 1e7;

typedef struct {
    double numerator[2], norm[2], lag_re[2], lag_im[2];
} ParityReadout;

/* The nominated epoch's timing and refinement templates and the three
   released confirmation ranges do not include these pilot symbols. */
static BlockReadout block_readout(const TwoCarrierReceiver *r, const int16_t *iq,
                                  int lane, TimingFirstResult p) {
    BlockReadout out = {.examined = 1, .hz = p.hz};
    double dr = cos(-readout_tau*p.hz/readout_rate), di = sin(-readout_tau*p.hz/readout_rate);
    double ar = 1., ai = 0.;
    double tr[held_size], ti[held_size], cr[held_size], ci[held_size];
    double tnorm[held_blocks] = {0.}, cnorm[held_blocks] = {0.};
    for (int n = 0; n < held_size; ++n) {
        PortableFineComplex t = r->true_pilot[held_start+n], c = r->rolled[held_start+n];
        tr[n] = t.r*ar + t.i*ai;
        ti[n] = t.r*ai - t.i*ar;
        cr[n] = c.r*ar + c.i*ai;
        ci[n] = c.r*ai - c.i*ar;
        tnorm[n / block_size] += t.r*t.r + t.i*t.i;
        cnorm[n / block_size] += c.r*c.r + c.i*c.i;
        double next = ar*dr - ai*di;
        ai = ar*di + ai*dr;
        ar = next;
    }
    int whole = (int)floor(p.epoch);
    double fraction = p.epoch - whole;
    out.offset = p.epoch - nearbyint(p.epoch);
    ParityReadout groups[2] = {0};
    for (int frame = 0; frame < 15; ++frame) {
        int start = (frame*40000 + 1)/3 + whole + held_start;
        if (start < 0 || start + held_size >= samples) break;
        ++out.frames;
        ParityReadout *g = &groups[frame & 1];
        double last_r[2] = {0.}, last_i[2] = {0.};
        for (int b = 0; b < held_blocks; ++b) {
            double a = 0., d = 0., c = 0., e = 0., power = 0.;
            #pragma omp simd reduction(+:a,d,c,e,power)
            for (int j = b*block_size; j < (b+1)*block_size; ++j) {
                const int16_t *x = iq + 4*(start+j) + 2*lane;
                double xr = x[0] + fraction*(x[4] - x[0]), xi = x[1] + fraction*(x[5] - x[1]);
                a += xr*tr[j] - xi*ti[j];
                d += xr*ti[j] + xi*tr[j];
                c += xr*cr[j] - xi*ci[j];
                e += xr*ci[j] + xi*cr[j];
                power += xr*xr + xi*xi;
            }
            const double values_r[] = {a, c}, values_i[] = {d, e};
            const double template_powers[] = {tnorm[b], cnorm[b]};
            for (int hypothesis = 0; hypothesis < 2; ++hypothesis) {
                double re = values_r[hypothesis], im = values_i[hypothesis];
                g->numerator[hypothesis] += re*re + im*im;
                g->norm[hypothesis] += power*template_powers[hypothesis];
                g->lag_re[hypothesis] += re*last_r[hypothesis] + im*last_i[hypothesis];
                g->lag_im[hypothesis] += im*last_r[hypothesis] - re*last_i[hypothesis];
                last_r[hypothesis] = re;
                last_i[hypothesis] = im;
            }
        }
    }
    if (out.frames < 8) return out;
    double power[2][2], df[2][2];
    for (int parity = 0; parity < 2; ++parity) {
        ParityReadout *g = &groups[parity];
        for (int hypothesis = 0; hypothesis < 2; ++hypothesis) {
            power[parity][hypothesis] = g->numerator[hypothesis]/fmax(g->norm[hypothesis], 1e-15);
            df[parity][hypothesis] = atan2(g->lag_im[hypothesis], g->lag_re[hypothesis])
                * readout_rate/(readout_tau*block_size);
        }
    }
    out.exact = fmin(power[0][0], power[1][0]);
    out.control = fmax(power[0][1], power[1][1]);
    for (int hypothesis = 0; hypothesis < 2; ++hypothesis) {
        int other = 1 - hypothesis;
        double signal = fmin(power[0][hypothesis], power[1][hypothesis]);
        double control = fmax(power[0][other], power[1][other]);
        double correction = atan2(groups[0].lag_im[hypothesis] + groups[1].lag_im[hypothesis],
                                  groups[0].lag_re[hypothesis] + groups[1].lag_re[hypothesis])
                           * readout_rate/(readout_tau*block_size);
        int accepted = signal - control >= .010 && fabs(correction) <= 1000.
            && fabs(df[0][hypothesis] - df[1][hypothesis]) <= 350.;
        if (!hypothesis) {
            out.accepted = accepted;
            out.hz += correction;
            out.group_hz[0] = df[0][hypothesis];
            out.group_hz[1] = df[1][hypothesis];
        } else {
            out.rolled_accepted = accepted;
        }
    }
    return out;
}

/* Mode 0 runs the pinned verifier, 1 traces that path, 2 omits all readout for
   the cost ceiling, and 3 runs the independent pilot blocks. Both scouts and
   signed cancellation are identical across arms. */
int scout_readout_run(TwoCarrierReceiver *r, const int16_t *iq, int lane, double lo,
                      double hi, int mode, ScanFactor out[2], ScoutReadoutTrace *trace) {
    if (!r || !iq || !out || lane < 0 || lane > 1 || mode < 0 || mode > 3) return -1;
    if (trace) *trace = (ScoutReadoutTrace){0};
    TimingFirstResult p[2] = {0};
    if (timing_first_detect(r->timing, iq, lane, lo, hi, &p[0])) return -1;
    if (trace) trace->scout[0] = p[0];
    if (!p[0].confirmation) return 0;
    int status;
    if ((lo + hi) / 2 == 0.) {
        status = timing_first_cancel_resident(r->timing, r->synthesis, r->rotated, &p[0], lo, hi, &p[1]);
    } else {
        status = pilot_cancel(iq, r->residual, lane, r->synthesis, r->rotated, p[0].epoch, p[0].hz) ||
                 timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1]);
    }
    if (status) return -1;
    if (trace) trace->scout[1] = p[1];
    if (mode == 2) return 0;
    uint64_t start = mode == 1 ? readout_cpu() : 0;
    if (mode != 3) {
        if (portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;
        if (mode == 1 && trace) {
            trace->loading_cpu_ns = readout_cpu() - start;
            start = readout_cpu();
        }
        TwoCarrierPeak peaks[2];
        readout_trace = mode == 1 ? trace : NULL;
        int count = verify_peaks(r, p, peaks, out, 1);
        readout_trace = NULL;
        if (mode == 1 && trace) trace->verification_cpu_ns = readout_cpu() - start;
        return count;
    }
    int count = 0;
    for (int rank = 0; rank < 2; ++rank) {
        if (!p[rank].confirmation || (rank && same_peak(p[0].epoch, p[0].hz, p[1].epoch, p[1].hz)))
            continue;
        BlockReadout measured = block_readout(r, iq, lane, p[rank]);
        if (trace) trace->block[rank] = measured;
        if (!measured.accepted || measured.hz < lo || measured.hz > hi ||
            (count && same_peak(out[0].integer + out[0].offset, out[0].hz,
                                p[rank].epoch, measured.hz))) continue;
        int epoch = (int)nearbyint(p[rank].epoch) % period;
        out[count++] = (ScanFactor){rank, epoch, measured.offset, measured.hz, measured.exact, measured.control};
    }
    if (count == 2 && out[1].exact - out[1].control > out[0].exact - out[0].control) {
        ScanFactor saved = out[0];
        out[0] = out[1];
        out[1] = saved;
    }
    return count;
}
