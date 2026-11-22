"""Build the experimental scout from the pinned two-scan timing and factor code."""

from .receiver_build import replace


def timing_overlay(source):
    edits = [
        ('#include "timing_first_receiver.h"', '#include "receiver_tracking.h"'),
        ('static void find_times(TimingFirst *w, int *epochs) {',
         'static void find_times(TimingFirst *w, int *epochs, int clocks_used, int shortened) {\n'
         '    const int short_lags[] = {1, 4};'),
        ('    for (int k = 0; k < lags; ++k) {\n        int lag',
         '    for (int index = 0; index < (shortened ? 2 : lags); ++index) {\n'
         '        int k = shortened ? short_lags[index] : index;\n        int lag'),
        ('    for (int k = 0; k < clocks; ++k) {', '    for (int k = 0; k < clocks_used; ++k) {'),
        ('                         Seed *all) {', '                         Seed *all, int clocks_used) {'),
        ('    for (int i = 0; i < clocks; ++i) {', '    for (int i = 0; i < clocks_used; ++i) {'),
        ('int timing_first_detect(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,\n'
         '                        TimingFirstResult *out) {',
         '#include "receiver_tracking_timing.inc"\n\n'
         'int experimental_timing_detect(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,\n'
         '                               TimingFirstResult *out, const TimingHint *hints, unsigned used, int mode) {'),
        ('    double center = (lo + hi) / 2;\n    input', '''    if (used > max_tracking_hints || (used && !hints)) return -1;
    Peak peaks[max_peaks];
    int done = 0;
    if (mode == 2) {
        input(w, iq, lane, 0.);
        for (unsigned i = 0; i < used; ++i) {
            int status = refine_hint(w, hints[i], lo, hi, &peaks[done]);
            if (status < 0) return -1;
            done += status;
        }
        find_confirmed(w, peaks, done, out);
        return 0;
    }
    int clocks_used = mode ? 3 : clocks, choices_used = mode ? 2 : choices;
    double center = (lo + hi) / 2;
    input'''),
        ('    find_times(w, epochs);', '    find_times(w, epochs, clocks_used, mode);'),
        ('    int n = find_carriers(w, epochs, lo, hi, center, seeds), done = 0;\n    Peak peaks[max_peaks];',
         '    int n = find_carriers(w, epochs, lo, hi, center, seeds, clocks_used);'),
        ('    for (int k = 0; k < choices && k < n; ++k) {',
         '    for (int k = 0; k < choices_used && k < n; ++k) {'),
    ]
    for old, new in edits:
        source = replace(source, old, new)
    end = source.index('    for (int k = 0; k < done; ++k) {', source.index('int experimental_timing_detect('))
    return source[:end] + '''    for (unsigned i = 0; i < used && done < max_peaks; ++i) {
        int status = refine_hint(w, hints[i], lo, hi, &peaks[done]);
        if (status < 0) return -1;
        done += status;
    }
    find_confirmed(w, peaks, done, out);
    return 0;
}

int timing_first_detect(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,
                        TimingFirstResult *out) {
    return experimental_timing_detect(w, iq, lane, lo, hi, out, NULL, 0, 0);
}
'''


def measure_overlay(source):
    edits = [
        ('#include "timing_first_receiver.h"', '#include "receiver_tracking.h"'),
        ('static int measure(', '#include "receiver_tracking_measure.inc"\n\nstatic int measure('),
        ('TwoCarrierPeak out[2], ScanFactor *factors) {',
         'TwoCarrierPeak out[2], ScanFactor *factors, const TrackingPlan *plan) {'),
        ('timing_first_detect(r->timing, iq, lane, lo, hi, &p[0])',
         'search_visit(r->timing, iq, lane, lo, hi, &p[0], plan, NULL)'),
        ('timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1])',
         'search_visit(r->timing, r->residual, lane, lo, hi, &p[1], plan, &p[0])'),
        ('measure(r, iq, lane, lo, hi, out, NULL)', 'measure(r, iq, lane, lo, hi, out, NULL, NULL)'),
        ('measure(r, iq, lane, lo, hi, peaks, out)', 'measure(r, iq, lane, lo, hi, peaks, out, NULL)'),
    ]
    for old, new in edits:
        source = replace(source, old, new)
    return source + '''
int cancellation_factors_tracking(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                                  double lo, double hi, const TimingHint *hints, unsigned count,
                                  int full, TrackingStats *stats, ScanFactor out[2]) {
    if (!stats || !out || count > max_tracking_hints || (count && !hints)) return -1;
    TrackingPlan plan = {hints, count, full, stats};
    TwoCarrierPeak peaks[2];
    int measured = measure(r, iq, lane, lo, hi, peaks, out, &plan);
    if (full || measured < 0) return measured;
    for (unsigned h = 0; h < count; ++h) {
        int supported = 0;
        for (int k = 0; k < measured; ++k) {
            supported |= fabs(remainder(peaks[k].epoch - hints[h].epoch, period)) <= 5. &&
                         fabs(peaks[k].hz - hints[h].hz) <= 1600.;
        }
        if (!supported) {
            ++stats->reacquire;
            plan.full = 1;
            return measure(r, iq, lane, lo, hi, peaks, out, &plan);
        }
    }
    return measured;
}
'''
