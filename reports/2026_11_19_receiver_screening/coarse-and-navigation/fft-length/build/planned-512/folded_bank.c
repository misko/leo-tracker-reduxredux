/* Evaluate the capture-era folded score by exact complex overlap-save FIRs.
 * Included by the folded-grid adapter with its original argument structure. */
#define FFTW_NO_Complex
#include <fftw3.h>

enum { fft_length = 512, maximum_taps = 64 };
#include "original_kernel_cache.h"

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

    int filter_ffts;
    kernel_cache_entry *ready=prepare_kernel(k,taps,&filter_ffts);
    if(!ready) { k->invalid_geometry=1; return; }
    const size_t filter_cells=(size_t)ns*nf*fft_length;
    fftwf_complex *filters=ready->filters, *input=ready->input, *spectrum=ready->spectrum,
        *inverse_input=ready->inverse_input, *output=ready->output;
    const fftwf_plan forward=ready->forward, inverse=ready->inverse;
    int common_taps=1;
    for(int s=1;s<ns;++s) if(taps[s]!=taps[0]) common_taps=0;

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
        memset(input + n, 0, (fft_length - n) * sizeof(fftwf_complex));
        fftwf_execute(forward);
        ++blocks;
        double common[fft_length];
        int available=remaining-max_taps+1;
        if(available>span) available=span;
        if(common_taps) {
            #pragma omp simd
            for(int t=0;t<available;++t) {
                const double energy=k->prefix[first+t+max_taps]-k->prefix[first+t];
                common[t]=energy>0 ? 1/sqrt(energy) : 0;
            }
        }
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
            double distinct[fft_length];
            const double *norm=common_taps ? common : distinct;
            if(!common_taps) {
                #pragma omp simd
                for(int t=0;t<limit;++t) {
                    const double energy=k->prefix[first+t+taps[s]]-k->prefix[first+t];
                    distinct[t]=energy>0 ? 1/sqrt(energy) : 0;
                }
            }
            const double template_weight=ready->inverse_ref[s];
            for (int f = 0; f < nf; ++f) {
                const fftwf_complex *filter = filters + ((size_t)s * nf + f) * fft_length;
                for (int j = 0; j < fft_length; ++j) {
                    const float xr = spectrum[j][0], xi = spectrum[j][1];
                    const float hr = filter[j][0], hi = filter[j][1];
                    inverse_input[f*fft_length+j][0] = xr * hr - xi * hi;
                    inverse_input[f*fft_length+j][1] = xr * hi + xi * hr;
                }
            }
            fftwf_execute(inverse);
            inverse_calls += nf;
            for (int f = 0; f < nf; ++f) {
                const fftwf_complex *lane = output + f*fft_length;
                double *row = k->scores + (size_t)f * ne;
                for (int m = 0; m < count; ++m) {
                    #pragma omp simd
                    for (int t = start[m]; t < stop[m]; ++t) {
                        const int j = t + taps[s] - 1;
                        const float xr = lane[j][0] / fft_length, xi = lane[j][1] / fft_length;
                        row[t + base[m]] += (double)sqrtf(xr * xr + xi * xi) * (norm[t]*template_weight);
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
            fft_length, blocks, inverse_calls, filter_ffts,
            (filter_cells + (2 + 2*(size_t)nf) * fft_length) * sizeof(fftwf_complex));

}
