/* Evaluate the capture-era folded score by exact complex overlap-save FIRs.
 * Included by the folded-grid adapter with its original argument structure. */
#define FFTW_NO_Complex
#include <fftw3.h>

enum { fft_length = 512, maximum_taps = 64 };

static int valid_epochs(const FoldedAnchorGridKernel *k, int taps, int base) {
    const int n = k->sample_count - taps + 1 - base;
    return n < k->epoch_count ? n : k->epoch_count;
}

static void LEO_GRID_FUNCTION(FoldedAnchorGridKernel *k) {
    const int ns = k->symbol_count, nf = k->cfo_count, ne = k->epoch_count;
    int taps[22], max_taps = 0;
    double energies[22];
    if (!k->fast_magnitude || ns < 1 || ns > 22 || nf < 1 || nf > 21 || ne < 1 ||
        k->offset_count < 1 || k->offset_count > 16) {
        k->invalid_geometry = 1;
        return;
    }
    for (int s = 0; s < ns; ++s) {
        taps[s] = k->stops[s] - k->starts[s];
        if (taps[s] < 1 || taps[s] > maximum_taps) {
            k->invalid_geometry = 1;
            return;
        }
        if (taps[s] > max_taps) max_taps = taps[s];
        energies[s] = 0.0;
        for (int t = 0; t < taps[s]; ++t) {
            const double complex ref = k->references[k->starts[s] + t];
            energies[s] += creal(ref) * creal(ref) + cimag(ref) * cimag(ref);
        }
        for (int m = 0; m < k->offset_count; ++m) {
            const int base = k->starts[s] + k->offsets[m];
            if (base < 0) {
                k->invalid_geometry = 1;
                return;
            }
            const int count = valid_epochs(k, taps[s], base);
            if (count <= 0) break;
            k->support[0]++;
            if (count < ne) k->support[count]--;
        }
    }
    for (int e = 1; e < ne; ++e) k->support[e] += k->support[e - 1];
    memset(k->scores, 0, (size_t)nf * ne * sizeof(double));

    const size_t filter_cells = (size_t)ns * nf * fft_length;
    fftw_complex *filters = fftw_alloc_complex(filter_cells);
    fftw_complex *input = fftw_alloc_complex(fft_length);
    fftw_complex *spectrum = fftw_alloc_complex(fft_length);
    fftw_complex *output = fftw_alloc_complex(fft_length);
    fftw_plan forward = NULL, inverse = NULL;
    if (!filters || !input || !spectrum || !output) goto cleanup;
    forward = fftw_plan_dft_1d(fft_length, input, spectrum, FFTW_FORWARD, FFTW_ESTIMATE);
    inverse = fftw_plan_dft_1d(fft_length, input, output, FFTW_BACKWARD, FFTW_ESTIMATE);
    if (!forward || !inverse) goto cleanup;
    double cosine[21][maximum_taps], sine[21][maximum_taps];
    for (int f = 0; f < nf; ++f) {
        for (int t = 0; t < max_taps; ++t) {
            const double phase = 6.283185307179586476925286766559 * k->frequencies[f] *
                                 t / k->sample_rate_hz;
            cosine[f][t] = cos(phase);
            sine[f][t] = sin(phase);
        }
    }
    for (int s = 0; s < ns; ++s) {
        for (int f = 0; f < nf; ++f) {
            memset(input, 0, fft_length * sizeof(fftw_complex));
            for (int t = 0; t < taps[s]; ++t) {
                const double complex ref = k->references[k->starts[s] + t];
                const double real = creal(ref), imag = cimag(ref);
                const int j = taps[s] - 1 - t;
                input[j][0] = real * cosine[f][t] - imag * sine[f][t];
                input[j][1] = -(real * sine[f][t] + imag * cosine[f][t]);
            }
            fftw_execute(forward);
            memcpy(filters + ((size_t)s * nf + f) * fft_length, spectrum,
                   fft_length * sizeof(fftw_complex));
        }
    }

    /* Circular convolution index t+L-1 equals the linear FIR on the valid span.
     * All filters reuse the same forward FFT of the original waveform block. */
    const int span = fft_length - max_taps + 1;
    int blocks = 0, inverse_calls = 0;
    for (int first = 0; first < k->sample_count; first += span) {
        int remaining = k->sample_count - first;
        const int n = remaining < fft_length ? remaining : fft_length;
        for (int t = 0; t < n; ++t) {
            const double complex sample = k->samples[first + t];
            input[t][0] = creal(sample);
            input[t][1] = cimag(sample);
        }
        memset(input + n, 0, (fft_length - n) * sizeof(fftw_complex));
        fftw_execute(forward);
        ++blocks;
        for (int s = 0; s < ns; ++s) {
            int start[16], stop[16], base[16], count = 0;
            int limit = remaining - taps[s] + 1;
            if (limit > span) limit = span;
            if (limit <= 0) continue;
            for (int m = 0; m < k->offset_count; ++m) {
                const int origin = k->starts[s] + k->offsets[m];
                if (origin >= first + limit) break;
                const int epochs = valid_epochs(k, taps[s], origin);
                const int lo = origin > first ? origin : first;
                const int hi = origin + epochs < first + limit ? origin + epochs : first + limit;
                if (hi <= lo) continue;
                start[count] = lo - first;
                stop[count] = hi - first;
                base[count++] = first - origin;
            }
            if (!count) continue;
            double norm[fft_length];
            for (int t = 0; t < limit; ++t) {
                const double e = k->prefix[first + t + taps[s]] - k->prefix[first + t];
                const double denominator = e > 0 ? sqrt(energies[s] * e) : 0.0;
                norm[t] = denominator > 0 ? 1.0 / denominator : 0.0;
            }
            for (int f = 0; f < nf; ++f) {
                const fftw_complex *filter = filters + ((size_t)s * nf + f) * fft_length;
                for (int j = 0; j < fft_length; ++j) {
                    const double xr = spectrum[j][0], xi = spectrum[j][1];
                    const double hr = filter[j][0], hi = filter[j][1];
                    input[j][0] = xr * hr - xi * hi;
                    input[j][1] = xr * hi + xi * hr;
                }
                fftw_execute(inverse);
                ++inverse_calls;
                double *row = k->scores + (size_t)f * ne;
                for (int m = 0; m < count; ++m) {
                    for (int t = start[m]; t < stop[m]; ++t) {
                        if (!norm[t]) continue;
                        const int j = t + taps[s] - 1;
                        const double xr = output[j][0] / fft_length, xi = output[j][1] / fft_length;
                        row[t + base[m]] += sqrt(xr * xr + xi * xi) * norm[t];
                    }
                }
            }
        }
    }
    for (int f = 0; f < nf; ++f) {
        double *row = k->scores + (size_t)f * ne;
        for (int e = 0; e < ne; ++e) {
            if (k->support[e] > 0) row[e] /= k->support[e];
        }
    }
    fprintf(stderr,
            "bank {\"fft_length\":%d,\"input_ffts\":%d,\"inverse_ffts\":%d,"
            "\"filter_ffts\":%d,\"fft_buffers_bytes\":%zu}\n",
            fft_length, blocks, inverse_calls, ns * nf,
            (filter_cells + 3 * fft_length) * sizeof(fftw_complex));

cleanup:
    if (!forward || !inverse) k->invalid_geometry = 1;
    if (forward) fftw_destroy_plan(forward);
    if (inverse) fftw_destroy_plan(inverse);
    fftw_free(filters);
    fftw_free(input);
    fftw_free(spectrum);
    fftw_free(output);
}
