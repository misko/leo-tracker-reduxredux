/* Center all evaluated dots once. Keep their exact original magnitude path. */
static const float phase_real[11] = COARSE_PHASE_REAL;
static const float phase_imag[11] = COARSE_PHASE_IMAG;
static const int even_index[10][COARSE_TERMS] = COARSE_EVEN_INDEX;

static void fold_cfo(const fftwf_complex *output, const float *weights, double *scores,
    int ne, int taps, int limit, const double *norm, double reference,
    const int *start, const int *stop, const int *base, int nframes)
{
    float real[11][fft_length], imag[11][fft_length];
    for (int lane = 0; lane < 11; ++lane) {
        const fftwf_complex *time = output + (size_t)lane * fft_length + taps - 1;
        const float cr = phase_real[lane], ci = phase_imag[lane];
        #pragma omp simd
        for (int t = 0; t < limit; ++t) {
            real[lane][t] = time[t][0] * cr - time[t][1] * ci;
            imag[lane][t] = time[t][0] * ci + time[t][1] * cr;
        }
        double *row = scores + (size_t)(2*lane) * ne;
        for (int m = 0; m < nframes; ++m) {
            #pragma omp simd
            for (int t = start[m]; t < stop[m]; ++t) {
                const float re = time[t][0] / fft_length, im = time[t][1] / fft_length;
                row[t + base[m]] += (double)sqrtf(re*re + im*im) * (norm[t] * reference);
            }
        }
    }
    for (int lane = 0; lane < 10; ++lane) {
        const float *w = weights + (size_t)lane * COARSE_TERMS;
        const float *rx[COARSE_TERMS], *ix[COARSE_TERMS];
        for (int p = 0; p < COARSE_TERMS; ++p) {
            rx[p] = real[even_index[lane][p]];
            ix[p] = imag[even_index[lane][p]];
        }
        double *row = scores + (size_t)(2*lane + 1) * ne;
        for (int m = 0; m < nframes; ++m) {
            #pragma omp simd
            for (int t = start[m]; t < stop[m]; ++t) {
                float re = 0, im = 0;
                #pragma GCC unroll 11
                for (int p = 0; p < COARSE_TERMS; ++p) {
                    re += w[p] * rx[p][t];
                    im += w[p] * ix[p][t];
                }
                re /= fft_length;
                im /= fft_length;
                row[t + base[m]] += (double)sqrtf(re*re + im*im) * (norm[t] * reference);
            }
        }
    }
}
