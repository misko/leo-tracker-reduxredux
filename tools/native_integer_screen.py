"""Research VNNI screen for integer IQ; never an exact inference kernel.

The reference is quantized, but sample conversion and int32 dot products are
exact on the admitted domain. A separate input-derived norm bound covers the
reference quantization. Unsupported inputs require complete FP64 inference.
"""

import numpy as np
from native_screen_bounds import bound as floating_bound

SETUP = '''#if defined(LEO_GRID_AVX2_12_REGISTER_ACCUMULATION)
    if (kernel->cfo_count != 24) {
        kernel->invalid_geometry = 1;
        return;
    }
    npy_intp maximum_taps = 0;
    double xmax = 0.0, rmax = 0.0;
    for (npy_intp s = 0; s < kernel->symbol_count; ++s) {
        const npy_intp n = stops[s] - starts[s];
        if (n > maximum_taps) maximum_taps = n;
        for (npy_intp i = starts[s]; i < stops[s]; ++i) {
            rmax = fmax(rmax, fabs(creal(references[i])));
            rmax = fmax(rmax, fabs(cimag(references[i])));
        }
    }
    for (npy_intp i = 0; i < kernel->sample_count; ++i) {
        const double a = creal(samples[i]), b = cimag(samples[i]);
        if (!isfinite(a) || !isfinite(b) || a != nearbyint(a) || b != nearbyint(b)
                || fabs(a) > 32767 || fabs(b) > 32767) {
            kernel->invalid_geometry = 1;
            return;
        }
        xmax = fmax(xmax, fmax(fabs(a), fabs(b)));
    }
    if (xmax == 0.0 || !isfinite(rmax) || rmax == 0.0 || maximum_taps <= 0) {
        kernel->invalid_geometry = 1;
        return;
    }
    const double qmax = fmin(32767.0, floor(2147483647.0 /
                                         (2.0 * maximum_taps * xmax))) - 1.0;
    const double scale = qmax / (2.0 * rmax);
    if (!(scale > 0.0) || !isfinite(scale)) {
        kernel->invalid_geometry = 1;
        return;
    }
    int16_t *qreal = malloc(maximum_taps * kernel->cfo_count * 2 * sizeof(int16_t));
    int16_t *qimag = malloc(maximum_taps * kernel->cfo_count * 2 * sizeof(int16_t));
    uint32_t *packed = malloc(kernel->sample_count * sizeof(uint32_t));
    if (!qreal || !qimag || !packed) {
        free(qreal); free(qimag); free(packed);
        kernel->invalid_geometry = 1;
        return;
    }
    for (npy_intp i = 0; i < kernel->sample_count; ++i) {
        const uint16_t a = (uint16_t)(int16_t)creal(samples[i]);
        const uint16_t b = (uint16_t)(int16_t)cimag(samples[i]);
        packed[i] = (uint32_t)a | ((uint32_t)b << 16);
    }
#else
    double *restrict rotated_real = kernel->rotated_real;
    double *restrict rotated_imag = kernel->rotated_imag;
#endif'''

ROTATION = '''#if defined(LEO_GRID_AVX2_12_REGISTER_ACCUMULATION)
                const int16_t qr = (int16_t)nearbyint(
                    (reference_real * cosine - reference_imag * sine) * scale);
                const int16_t qi = (int16_t)nearbyint(
                    (reference_real * sine + reference_imag * cosine) * scale);
                qreal[2 * rotated_index] = qr;
                qreal[2 * rotated_index + 1] = qi;
                qimag[2 * rotated_index] = -qi;
                qimag[2 * rotated_index + 1] = qr;
#else
                rotated_real[rotated_index] =
                    reference_real * cosine - reference_imag * sine;
                rotated_imag[rotated_index] =
                    reference_real * sine + reference_imag * cosine;
#endif'''

CORRELATION = '''                __m256i cr0 = _mm256_setzero_si256();
                __m256i cr1 = _mm256_setzero_si256();
                __m256i cr2 = _mm256_setzero_si256();
                __m256i ci0 = _mm256_setzero_si256();
                __m256i ci1 = _mm256_setzero_si256();
                __m256i ci2 = _mm256_setzero_si256();
                for (npy_intp i = 0; i < reference_count; ++i) {
                    const __m256i x = _mm256_set1_epi32((int32_t)packed[position + i]);
                    const npy_intp j = i * 48;
                    cr0 = _mm256_dpwssd_avx_epi32(cr0, x,
                        _mm256_loadu_si256((const __m256i *)(qreal+j)));
                    cr1 = _mm256_dpwssd_avx_epi32(cr1, x,
                        _mm256_loadu_si256((const __m256i *)(qreal+j+16)));
                    cr2 = _mm256_dpwssd_avx_epi32(cr2, x,
                        _mm256_loadu_si256((const __m256i *)(qreal+j+32)));
                    ci0 = _mm256_dpwssd_avx_epi32(ci0, x,
                        _mm256_loadu_si256((const __m256i *)(qimag+j)));
                    ci1 = _mm256_dpwssd_avx_epi32(ci1, x,
                        _mm256_loadu_si256((const __m256i *)(qimag+j+16)));
                    ci2 = _mm256_dpwssd_avx_epi32(ci2, x,
                        _mm256_loadu_si256((const __m256i *)(qimag+j+32)));
                }
                int32_t cr[24], ci[24];
                _mm256_storeu_si256((__m256i *)cr, cr0);
                _mm256_storeu_si256((__m256i *)(cr+8), cr1);
                _mm256_storeu_si256((__m256i *)(cr+16), cr2);
                _mm256_storeu_si256((__m256i *)ci, ci0);
                _mm256_storeu_si256((__m256i *)(ci+8), ci1);
                _mm256_storeu_si256((__m256i *)(ci+16), ci2);
                for (int f = 0; f < 24; ++f) {
                    correlation_real[f] = cr[f] / scale;
                    correlation_imag[f] = ci[f] / scale;
                }
'''


def transform(source, grid):
    marker = '#if defined(LEO_GRID_AVX2_12_REGISTER_ACCUMULATION)'
    begin = grid.index(marker)
    end = grid.index('                double received_energy =', begin)
    branch = grid[begin:end]
    split = branch.index('} else {')
    generic = branch[split + len('} else {'):]
    generic = generic.replace('#endif\n', '', 1)
    generic = generic[:generic.index(marker)]
    # Keep the outer LEO_GRID_CORRELATE #else/#endif surrounding this block.
    grid = grid[:begin] + marker + '\n' + CORRELATION + '#else\n' + generic + (
        '#endif\n#endif\n') + grid[end:]
    declarations = ('    double *restrict rotated_real = kernel->rotated_real;\n'
                    '    double *restrict rotated_imag = kernel->rotated_imag;')
    rotation = ROTATION.split('#else\n')[1].split('#endif')[0].rstrip()
    if grid.count(declarations) != 1 or grid.count(rotation) != 1:
        raise ValueError('Unknown grid reference layout')
    grid = grid.replace(declarations, SETUP).replace(rotation, ROTATION)
    grid = grid.replace('    kernel->invalid_geometry = invalid_geometry;',
                        '#if defined(LEO_GRID_AVX2_12_REGISTER_ACCUMULATION)\n'
                        '    free(qreal); free(qimag); free(packed);\n#endif\n'
                        '    kernel->invalid_geometry = invalid_geometry;')
    if source.count('cfo_count == 12') != 1:
        raise ValueError('Unknown native dispatch')
    source = source.replace('cfo_count == 12', 'cfo_count == 24')
    source = source.replace('avx2,fma,tune=haswell', 'avx2,fma,avxvnni,tune=haswell')
    source = source.replace('__builtin_cpu_supports("fma")',
                            '__builtin_cpu_supports("fma") && __builtin_cpu_supports("avxvnni")')
    source = source.replace('#include <math.h>',
                            '#include <math.h>\n#include <stdint.h>\n#include <stdlib.h>')
    return source, grid


def bound(acquisition, args):
    result = floating_bound(acquisition, args)
    if not result['eligible']:
        return result
    values, template, rate, frequencies, symbols, epochs = args
    if (np.any(values.real != np.rint(values.real))
            or np.any(values.imag != np.rint(values.imag))
            or result['max_sample_component'] > 32767):
        return dict(eligible=False, reason='integer screen requires signed integer IQ')
    starts = [round(s * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols]
    stops = [round((s + 1) * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols]
    rmax = max(max(np.max(np.abs(template[s:t].real)), np.max(np.abs(template[s:t].imag)))
               for s, t in zip(starts, stops, strict=True))
    qmax = min(32767., np.floor((2.**31 - 1) /
                               (2 * result['max_taps'] * result['max_sample_component']))) - 1
    scale = qmax / (2*rmax)
    if not np.isfinite(scale) or scale <= 0:
        return dict(eligible=False, reason='unsafe integer accumulation scale')
    # Each rotated reference component rounds by at most .5/scale. Allow a
    # factor two for reference-norm estimation and quantization arithmetic.
    relative = max(np.sqrt(2*(t-s)) / (scale*np.linalg.norm(template[s:t]))
                   for s, t in zip(starts, stops, strict=True))
    error = relative*np.sqrt(result['maximum_energy_ratio']) + 1e-10*(1+relative)
    return dict(result, absolute_error=float(np.nextafter(error, np.inf)),
                reference_scale=float(scale), quantized_maximum=float(qmax),
                error_model='integer IQ / int16 reference quantization norm bound',
                production_qualified=False)
