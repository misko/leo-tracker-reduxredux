"""Attach the lane-local linear scout to the pinned detector's measured gates."""

from .receiver_build import replace


def timing_overlay(source):
    edits = [
        ('#include "timing_first_receiver.h"', '#include "receiver_projection.h"'),
        ('    float fir[81];', '    float fir[81];\n    Sample *linear_filters, *linear_input, *linear_low;'),
        ('void timing_first_free(', 'static int prepare_projection(TimingFirst *w);\n\nvoid timing_first_free('),
        ('    free(w->power);', '    free(w->power);\n    free(w->linear_filters);\n'
         '    free(w->linear_input);\n    free(w->linear_low);'),
        ('    prepare(w);', '    prepare(w);\n    if (!prepare_projection(w)) {\n'
         '        timing_first_free(w);\n        return NULL;\n    }'),
    ]
    for old, new in edits:
        source = replace(source, old, new)
    return source + '\n#include "receiver_projection_timing.inc"\n'


def measure_overlay(source):
    edits = [
        ('#include "timing_first_receiver.h"', '#include "receiver_projection.h"'),
        ('TwoCarrierPeak out[2], ScanFactor *factors) {',
         'TwoCarrierPeak out[2], ScanFactor *factors, ProjectionVisit *projection, int exact_first) {'),
        ('    if (timing_first_detect(r->timing, iq, lane, lo, hi, &p[0])) return -1;', '''    int first_status = projection ? projection_detect(r->timing, iq, NULL, lane, lo, hi, &p[0],
                                                      &projection->scan[0])
                                  : timing_first_detect(r->timing, iq, lane, lo, hi, &p[0]);
    if (!first_status && exact_first)
        first_status = timing_first_detect(r->timing, iq, lane, lo, hi, &p[0]);
    if (first_status) return -1;'''),
        ('        timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1]) ||',
         '        (projection ? projection_detect(r->timing, r->residual, iq, lane, lo, hi, &p[1],\n'
         '                                       &projection->scan[1])\n'
         '                    : timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1])) ||'),
        ('measure(r, iq, lane, lo, hi, out, NULL)', 'measure(r, iq, lane, lo, hi, out, NULL, NULL, 0)'),
        ('measure(r, iq, lane, lo, hi, peaks, out)', 'measure(r, iq, lane, lo, hi, peaks, out, NULL, 0)'),
    ]
    for old, new in edits:
        source = replace(source, old, new)
    return source + '''
int cancellation_factors_projection(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                                    double lo, double hi, int mode, ProjectionVisit *trace,
                                    ScanFactor out[2]) {
    if (!out || !trace) return -1;
    *trace = (ProjectionVisit){0};
    TwoCarrierPeak peaks[2];
    int count = measure(r, iq, lane, lo, hi, peaks, out, trace, mode == 2);
    if (count < 0 || mode != 1 || trace->scan[0].zero) return count;
    /* A nonzero unscored support can reach the unit normalized correlation
       bound. The short aperture cannot certify release ranking there. */
    trace->fallback = 1;
    return measure(r, iq, lane, lo, hi, peaks, out, NULL, 0);
}
'''
