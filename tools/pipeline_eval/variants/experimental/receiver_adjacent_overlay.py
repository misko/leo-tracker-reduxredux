"""Use the historical full-rate adjacent-symbol score as both phase scouts."""

from textwrap import dedent, indent

from .receiver_build import replace


def fold_overlay(source):
    begin = source.index('void leo_differential_scout(')
    loop = source.index('    for (int lane = 0; lane < receivers; ++lane) {\n', begin)
    end = source.rindex('    }\n}')
    body = dedent(source[source.index('\n', loop) + 1:end])
    body = replace(body, 'double *lane_scores = scores + lane * frame;',
                   'double *lane_scores = scores;')
    prefix = replace(source[:begin], 'typedef struct {', 'typedef struct scout_context {')
    signature = ('void leo_differential_scout_lane(scout_context *s, '
                 'const int16_t *data, int lane,\n'
                 '                                const fftwf_complex *filters, '
                 'const double *energy, double *scores) {\n')
    return prefix + signature + indent(body, '    ') + '}\n'


def timing_overlay(source):
    edits = [
        ('#include "timing_first_receiver.h"', '#include "receiver_adjacent.h"'),
        ('    float fir[81];', '''    float fir[81];
    scout_context *adjacent;
    const DifferentialFilter *adjacent_filters;
    const double *adjacent_energy;
    AdjacentStats *adjacent_stats;
    int adjacent_fallback;'''),
        ('    free(w->power);',
         '    free(w->power);\n    leo_differential_scout_destroy(w->adjacent);'),
        ('                         Seed *all) {',
         '                         Seed *all, const int *native, int used_clocks) {'),
        ('    for (int i = 0; i < clocks; ++i) {', '    for (int i = 0; i < used_clocks; ++i) {'),
        ('epochs[i] * w->stride, best};', '(native ? native[i] : epochs[i] * w->stride), best};'),
        ('find_carriers(w, epochs, lo, hi, center, seeds)',
         'find_carriers(w, epochs, lo, hi, center, seeds, native, used)'),
    ]
    for old, new in edits:
        source = replace(source, old, new)
    signature = source.index('int timing_first_detect(')
    modes = '    principal_modes(w, low);'
    split = source.index(modes, signature) + len(modes)
    selection = source.index('    Seed seeds[2 * clocks];', split)
    helper = '''#include "receiver_adjacent_timing.inc"

static int select_from_epochs(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,
                              double center, const int *epochs, const int *native, int used,
                              TimingFirstResult *out) {
''' + source[selection:]
    return source[:signature] + helper + '\n' + source[signature:split] + '''
    int epochs[clocks], native[clocks];
    if (w->adjacent_stats) {
        unsigned scan = w->adjacent_stats->scouts++;
        if (!w->adjacent || scan >= 2) return -1;
        int used = adjacent_epochs(w, iq, lane, epochs, native);
        if (select_from_epochs(w, iq, lane, lo, hi, center, epochs, native, used, out)) return -1;
        if (out->confirmation) {
            w->adjacent_stats->confirmed[scan] = 1;
            return 0;
        }
        if (!w->adjacent_fallback) return 0;
        w->adjacent_stats->fallback[scan] = 1;
    }
    find_times(w, epochs);
    return select_from_epochs(w, iq, lane, lo, hi, center, epochs, NULL, clocks, out);
}
'''


def measure_overlay(source):
    source = replace(source, '#include "timing_first_receiver.h"', '#include "receiver_adjacent.h"')
    return source + '''
int receiver_adjacent_configure(TwoCarrierReceiver *r, const DifferentialFilter *filters,
                                const double *energy) {
    return r ? timing_adjacent_configure(r->timing, filters, energy) : -1;
}

int receiver_adjacent_factors(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                              double lo, double hi, int use_fallback,
                              AdjacentStats *stats, ScanFactor out[2]) {
    if (!r || !stats || !out) return -1;
    *stats = (AdjacentStats){0};
    timing_adjacent_mode(r->timing, stats, use_fallback);
    TwoCarrierPeak peaks[2];
    int status = measure(r, iq, lane, lo, hi, peaks, out);
    timing_adjacent_mode(r->timing, NULL, 0);
    return status;
}
'''
