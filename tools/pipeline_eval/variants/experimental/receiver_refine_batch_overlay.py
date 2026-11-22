"""Build an exact bank around the original CFO rotation and peak ranking."""

from .receiver_build import replace


def kernel_overlay(source):
    reference = source[source.index('int delay_refine('):]
    start = reference.index('    float hr[pilot], hiq[pilot];')
    split = reference.index('    double score[9], freqs[9];', start)
    prepare = replace(reference[start:split], '    float hr[pilot], hiq[pilot];',
                      '    float *hr = v->real, *hiq = v->imag;')
    finish = reference[split:]
    finish = replace(finish, '        int e=(epoch+i-4+period)%period;\n', '')
    begin = finish.index('            int offset=')
    end = finish.index('                zr[f][b]=a;', begin)
    finish = finish[:begin] + '''            for (int b = 0; b < 8; ++b) {
                LateCorrelation v = matrix[i][f][b];
                float a = v.real, c = v.imag, power = v.power;
''' + finish[end:]
    return source + '''
#include "receiver_refine_batch.h"

typedef struct { float real[pilot], imag[pilot]; double energy; } RefineRotation;
typedef LateCorrelation BlockMatrix[9][frames][8];

static void prepare_refine_rotation(const float *h, double hz, RefineRotation *v) {
''' + prepare + '''    v->energy = energy;
}

static int finish_refine(int epoch, double hz, double lo, double hi, double energy,
                         const BlockMatrix matrix, double out[4]) {
''' + finish + '\n#include "receiver_refine_batch.inc"\n'


def timing_overlay(source):
    source = '#include "receiver_refine_batch.h"\n' + source
    source = replace(source, '    Peak peaks[max_peaks];',
                     '    Peak peaks[max_peaks];\n    RefineRequest request[max_peaks];')
    original = '''            double v[4];
            if (delay_refine((float *)w->data, (float *)(w->pilot + first), selected.epoch,
                             base + branch * w->rate, lo, hi, v))
                return -1;
            peaks[done++] = (Peak){v[0], v[1], v[3], (int)v[2]};'''
    source = replace(source, original,
                     '''            request[done++] = (RefineRequest){selected.epoch,
                                                   base + branch * w->rate};''')
    return replace(source, '    for (int k = 0; k < done; ++k) {',
                   '''    double v[max_peaks][4];
    if (delay_refine_bank((float *)w->data, (float *)(w->pilot + first), request, done, lo, hi, v))
        return -1;
    for (int k = 0; k < done; ++k)
        peaks[k] = (Peak){v[k][0], v[k][1], v[k][3], (int)v[k][2]};
    for (int k = 0; k < done; ++k) {''')
