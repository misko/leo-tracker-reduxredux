/* Compress a mixed template/IQ product into centered local moments. */

#include <stdint.h>

#ifdef LEO_DIRECT_KERNEL
typedef int16_t IqScalar;
#else
typedef double IqScalar;
#endif

enum { block_size = 256, terms = 6 };

static void moments(const IqScalar *iq, const double *ref, int count,
                    const double *powers, double *out, double *energy)
{
    double power = 0;
    for (int component = 0; component < 2; ++component) {
        double a0 = 0, a1 = 0, a2 = 0, a3 = 0, a4 = 0, a5 = 0;
        #pragma omp simd reduction(+:a0, a1, a2, a3, a4, a5, power)
        for (int i = 0; i < count; ++i) {
            double re = iq[2 * i], im = iq[2 * i + 1];
            double cr = ref[2 * i], ci = ref[2 * i + 1];
            double value = component == 0 ? re * cr - im * ci : re * ci + im * cr;
            double lane = component == 0 ? re : im;
            power += lane * lane;
            a0 += value;
            a1 += value * powers[i];
            a2 += value * powers[block_size + i];
            a3 += value * powers[2 * block_size + i];
            a4 += value * powers[3 * block_size + i];
            a5 += value * powers[4 * block_size + i];
        }
        out[component] = a0;
        out[2 + component] = a1;
        out[4 + component] = a2;
        out[6 + component] = a3;
        out[8 + component] = a4;
        out[10 + component] = a5;
    }
    *energy += power;
}

void conditioned_moments(
    const IqScalar *restrict iq, const double *restrict reference,
    const int32_t *restrict starts, int frames, int samples, const double *restrict powers,
    double *restrict out, double *restrict energy)
{
    int blocks = (samples + block_size - 1) / block_size;
    for (int frame = 0; frame < frames; ++frame) {
        const IqScalar *row = iq + 2 * starts[frame];
        energy[frame] = 0;
        for (int b = 0; b < blocks; ++b) {
            int first = b * block_size;
            int count = samples - first < block_size ? samples - first : block_size;
            moments(row + 2 * first, reference + 2 * first, count, powers,
                    out + 2 * (frame * blocks + b) * terms, energy + frame);
        }
    }
}

void conditioned_single(
    const IqScalar *restrict iq, const double *restrict reference,
    const int32_t *restrict starts, int frames, int samples, double *restrict out)
{
    for (int frame = 0; frame < frames; ++frame) {
        const IqScalar *row = iq + 2 * starts[frame];
        double real = 0, imag = 0;
        #pragma omp simd reduction(+:real, imag)
        for (int i = 0; i < samples; ++i) {
            double re = row[2 * i], im = row[2 * i + 1];
            double cr = reference[2 * i], ci = reference[2 * i + 1];
            real += re * cr - im * ci;
            imag += re * ci + im * cr;
        }
        out[2 * frame] = real;
        out[2 * frame + 1] = imag;
    }
}
