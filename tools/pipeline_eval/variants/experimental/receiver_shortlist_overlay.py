"""Instrument the existing nonlinear first scout without changing its decisions."""

from .receiver_build import replace


def timing_overlay(source):
    edits = [
        ('#include "timing_first_receiver.h"', '#include "receiver_shortlist.h"'),
        ('static void find_times(TimingFirst *w, int *epochs) {', '''static void audit_timing_grid(const TimingFirst *);
static void audit_carrier_grid(const TimingFirst *, int, int, const uint16_t *, int,
                               double, double, double);

static void find_times(TimingFirst *w, int *epochs) {'''),
        ('    int radius = (int)nearbyint(6. / w->stride);',
         '    audit_timing_grid(w);\n    int radius = (int)nearbyint(6. / w->stride);'),
        ('        int prev = -1;', '        audit_carrier_grid(w, epochs[i] * w->stride, i + 1, eligible,\n'
         '                           eligible_count, lo, hi, center);\n        int prev = -1;'),
        ('int timing_first_detect(TimingFirst *w,',
         '#include "receiver_shortlist_timing.inc"\n\nint timing_first_detect(TimingFirst *w,'),
        ('    for (int k = 0; k < choices && k < n; ++k) {',
         '    if (audit_before_pruning(w, seeds, n, lo, hi, center)) return -1;\n'
         '    for (int k = 0; k < choices && k < n; ++k) {'),
        ('            peaks[done++] = (Peak){v[0], v[1], v[3], (int)v[2]};',
         '            Peak peak = (Peak){v[0], v[1], v[3], (int)v[2]};\n'
         '            record_first_choice(peak, selected.epoch, base + branch * w->rate);\n'
         '            peaks[done++] = peak;'),
    ]
    for old, new in edits:
        source = replace(source, old, new)
    return source


def measure_overlay(source):
    edits = [
        ('#include "timing_first_receiver.h"', '#include "receiver_shortlist.h"'),
        ('TwoCarrierPeak out[2], ScanFactor *factors) {',
         'TwoCarrierPeak out[2], ScanFactor *factors, ShortlistFast *fast) {'),
        ('''    if (timing_first_detect(r->timing, iq, lane, lo, hi, &p[0])) return -1;
    if (!p[0].confirmation) return 0;
    if (pilot_cancel(iq, r->residual, lane, r->synthesis, r->rotated, p[0].epoch, p[0].hz) ||
        timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1]) ||
        portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;''', '''    SecondSeed seed;
    int has_alternative = 0;
    int status = fast ? timing_shortlist_pair(r->timing, iq, lane, lo, hi, &p[0], &seed, &has_alternative)
                      : timing_first_detect(r->timing, iq, lane, lo, hi, &p[0]);
    if (status) return -1;
    if (!p[0].confirmation) return 0;
    if (pilot_cancel(iq, r->residual, lane, r->synthesis, r->rotated, p[0].epoch, p[0].hz)) return -1;
    int local = 0;
    if (fast) {
        ++fast->first_confirmed;
        if (has_alternative && !same_peak(p[0].epoch, p[0].hz, seed.raw.epoch, seed.raw.hz)) {
            ++fast->narrow_trials;
            if (timing_shortlist_residual(r->timing, r->residual, lane, lo, hi, seed, &p[1])) return -1;
            local = p[1].confirmation && !same_peak(p[0].epoch, p[0].hz, p[1].epoch, p[1].hz);
            fast->local_confirmed += local;
        }
        fast->full_residual += !local;
    }
    if ((!local && timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1])) ||
        portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;'''),
        ('measure(r, iq, lane, lo, hi, out, NULL)', 'measure(r, iq, lane, lo, hi, out, NULL, NULL)'),
        ('measure(r, iq, lane, lo, hi, peaks, out)', 'measure(r, iq, lane, lo, hi, peaks, out, NULL)'),
    ]
    for old, new in edits:
        source = replace(source, old, new)
    return source + '''
int receiver_shortlist_fast(TwoCarrierReceiver *r, const int16_t *iq, int lane, double lo, double hi,
                            ShortlistFast *stats, ScanFactor out[2]) {
    if (!stats || !out) return -1;
    *stats = (ShortlistFast){0};
    TwoCarrierPeak peaks[2];
    int count = measure(r, iq, lane, lo, hi, peaks, out, stats);
    if (count < 0 || !stats->local_confirmed) return count;
    for (int k = 0; k < count; ++k)
        if (out[k].rank == 1) return count;
    stats->full_retry = 1;
    ++stats->full_residual;
    return measure(r, iq, lane, lo, hi, peaks, out, NULL);
}

int receiver_audit_shortlist(TwoCarrierReceiver *r, const int16_t *iq, int lane, double lo, double hi,
                             double epoch, double hz, ShortlistAudit *result) {
    if (!r || !result) return -1;
    *result = (ShortlistAudit){.epoch = epoch, .hz = hz};
    if (timing_shortlist_audit(r->timing, iq, lane, lo, hi, result)) return -1;
    if (!result->confirmed_rank) return 0;
    if (portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;
    for (int i = 0; i < result->candidates; ++i) {
        AuditPeak p = result->peaks[i];
        if (!p.confirmed) continue;
        unsigned integer = (unsigned)nearbyint(p.epoch) % period;
        PortableVerifierResult v = {.acquired_hz = p.hz};
        if (portable_verifier_factor(r->verify, integer, &v)) return -1;
        if (!(v.flags & PORTABLE_VERIFIER_FRACTIONAL_GATE)) continue;
        double e = fmod(integer + v.offset_samples + period, period);
        double f = p.hz + v.fractional_residual_hz;
        if (same_peak(p.epoch, p.hz, e, f) && same_peak(epoch, hz, e, f)) {
            result->verified_rank = p.rank;
            break;
        }
    }
    return 0;
}
'''
