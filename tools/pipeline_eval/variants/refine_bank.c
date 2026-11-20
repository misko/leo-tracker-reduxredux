/* Capture-era GLRT64 correlations with the NumPy pairwise reduction order. */
#include <math.h>
#include <stdint.h>

enum { symbols = 64, taps = 44, aperture = symbols * taps, lanczos_taps = 16, lanes = 4 };

typedef struct { double re, im; } complex64x2;

static inline complex64x2 add(complex64x2 a, complex64x2 b)
{
    return (complex64x2) {a.re + b.re, a.im + b.im};
}

static inline complex64x2 mul(complex64x2 a, complex64x2 b)
{
    /* NumPy's X86_V3 complex ufunc multiplies the imaginary lane first. */
    return (complex64x2) {fma(a.re, b.re, -a.im * b.im), fma(a.re, b.im, a.im * b.re)};
}

static inline complex64x2 pairwise_sum(const complex64x2 *lane)
{
    return add(add(lane[0], lane[1]), add(lane[2], lane[3]));
}

static inline complex64x2 interpolate(const complex64x2 *values, const double *weights)
{
    complex64x2 lane[lanes];
    for (int t = 0; t < lanes; ++t)
        lane[t] = (complex64x2) {values[t].re * weights[t], values[t].im * weights[t]};
    for (int t = lanes; t < lanczos_taps; t += lanes)
        for (int k = 0; k < lanes; ++k) {
            double w = weights[t + k];
            complex64x2 sample = values[t + k];
            lane[k].re += sample.re * w;
            lane[k].im += sample.im * w;
        }
    return pairwise_sum(lane);
}

static inline void accumulate(
    complex64x2 sample, const complex64x2 *exact, const complex64x2 *control,
    int tap, complex64x2 *exact_lanes, complex64x2 *control_lanes)
{
    int k = tap % lanes;
    complex64x2 term_exact = mul(exact[tap], sample);
    complex64x2 term_control = mul(control[tap], sample);
    exact_lanes[k] = tap < lanes ? term_exact : add(exact_lanes[k], term_exact);
    control_lanes[k] = tap < lanes ? term_control : add(control_lanes[k], term_control);
}

void correlated_integer(
    const complex64x2 *restrict iq, const int32_t *restrict starts, int candidates, int frames,
    const int32_t *restrict rotation_row, const complex64x2 *restrict rotation,
    const complex64x2 *restrict exact, const complex64x2 *restrict control,
    complex64x2 *restrict exact_out, complex64x2 *restrict control_out)
{
    for (int c = 0; c < candidates; ++c) {
        const complex64x2 *phase = rotation + rotation_row[c] * aperture;
        for (int f = 0; f < frames; ++f) {
            int index = c * frames + f;
            if (starts[index] < 0) continue;
            const complex64x2 *received = iq + starts[index];
            for (int s = 0; s < symbols; ++s) {
                complex64x2 exact_lanes[lanes], control_lanes[lanes];
                int offset = s * taps;
                for (int t = 0; t < taps; ++t) {
                    complex64x2 corrected = mul(received[offset + t], phase[offset + t]);
                    accumulate(corrected, exact + offset, control + offset, t,
                               exact_lanes, control_lanes);
                }
                exact_out[index * symbols + s] = pairwise_sum(exact_lanes);
                control_out[index * symbols + s] = pairwise_sum(control_lanes);
            }
        }
    }
}

void correlated_fractional(
    const complex64x2 *restrict iq, const int32_t *restrict starts, int frames,
    const int32_t *restrict weight_row, const double *restrict weights,
    const complex64x2 *restrict rotation,
    const complex64x2 *restrict exact, const complex64x2 *restrict control,
    complex64x2 *restrict exact_out, complex64x2 *restrict control_out)
{
    for (int f = 0; f < frames; ++f) {
        for (int s = 0; s < symbols; ++s) {
            complex64x2 exact_lanes[lanes], control_lanes[lanes];
            int offset = s * taps;
            for (int t = 0; t < taps; ++t) {
                int index = f * aperture + offset + t;
                complex64x2 sample = interpolate(iq + starts[index],
                    weights + weight_row[index] * lanczos_taps);
                complex64x2 corrected = mul(sample, rotation[index]);
                accumulate(corrected, exact + offset, control + offset, t,
                           exact_lanes, control_lanes);
            }
            exact_out[f * symbols + s] = pairwise_sum(exact_lanes);
            control_out[f * symbols + s] = pairwise_sum(control_lanes);
        }
    }
}
