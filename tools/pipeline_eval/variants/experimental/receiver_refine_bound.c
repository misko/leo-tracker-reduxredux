/* Include the archived reductions under private names so the frozen receiver
   can still resolve its own decimation, bank and wrap-aware refinement. */
#define delay_decimate audit_delay_decimate
#define delay_refine audit_delay_refine
#define delay_refine_bank audit_delay_refine_bank
#include "delay_product_kernel.c"
#undef delay_decimate
#undef delay_refine
#undef delay_refine_bank

/* Relative error allowance after the Float32 block reductions.  Their exact
   recorded values are the inputs here and in finish_refine. */
static const double allowance = 0x1p-34;

__attribute__((target("avx2")))
static void correlate_parity(const float *x, const RefineRotation *rotation,
                             int epoch, int parity, BlockMatrix *matrix)
{
    const RefineRotation *rotations[] = {rotation};
    for (int f = parity; f < frames; f += 2) {
        int begin = (40000*f + 1)/3 + 88 + epoch - 4;
        const float *iq = x + 2*begin;
        for (int b = 0; b < 8; ++b) {
            int chains = b < 4 ? 4 : 1;
            refine_eight(iq, rotations, 1, b*block, chains, matrix, f, b);
            refine_last(iq + 16, rotations, 1, b*block, chains, matrix, f, b);
        }
    }
}

static int triangle_below(const BlockMatrix matrix, double energy, double cutoff)
{
    for (int i = 0; i < 9; ++i) {
        double bound = 0., power = 0.;
        for (int f = 0; f < frames; f += 2) {
            double norm = 0.;
            for (int b = 0; b < 8; ++b) {
                LateCorrelation z = matrix[i][f][b];
                double re = z.real, im = z.imag;
                norm += sqrt(re*re + im*im);
                power += z.power;
            }
            bound += norm * norm;
        }
        double denominator = fmax(power * energy, 1e-15);
        double upper = nextafter((bound + 2.*allowance*bound + 0x1p-900) / denominator, INFINITY);
        if (!isfinite(power * energy) || !(upper < cutoff)) return 0;
    }
    return 1;
}

__attribute__((target("avx2")))
static int prune_avx2(const float *x, const float *h, RefineRequest request,
                      double lo, double hi, double cutoff, double out[4])
{
    RefineRotation prepared;
    BlockMatrix matrix;
    prepare_refine_rotation(h, request.hz, &prepared);
    correlate_parity(x, &prepared, request.epoch, 0, &matrix);
    if (triangle_below(matrix, prepared.energy, cutoff)) return 1;
    correlate_parity(x, &prepared, request.epoch, 1, &matrix);
    return finish_refine(request.epoch, request.hz, lo, hi, prepared.energy, matrix, out);
}

int receiver_refine_prune(const float *x, const float *h, RefineRequest request,
                          double lo, double hi, double cutoff, double out[4])
{
    if (!safe_request(request) || !isfinite(cutoff) || !(cutoff > 0.) ||
        !__builtin_cpu_supports("avx2")) return 2;
    return prune_avx2(x, h, request, lo, hi, cutoff, out);
}

static void enclose_offset(const BlockMatrix matrix, int i, int parity,
                           double energy, double *triangle, double *restricted)
{
    enum { blocks = 8, intervals = 8 };
    double power = 0., broad = 0., absolute = 0.;
    double cr[blocks] = {0.}, ci[blocks] = {0.};
    for (int f = parity; f < frames; f += 2) {
        double norm = 0., magnitude = 0.;
        for (int b = 0; b < blocks; ++b) {
            LateCorrelation z = matrix[i][f][b];
            double re = z.real, im = z.imag;
            power += z.power;
            norm += hypot(re, im);
            magnitude += fabs(re) + fabs(im);
            for (int j = 0; j <= b; ++j) {
                LateCorrelation y = matrix[i][f][j];
                cr[b-j] += re*y.real + im*y.imag;
                ci[b-j] += im*y.real - re*y.imag;
            }
        }
        broad += norm * norm;
        absolute += magnitude * magnitude;
    }

    /* The angle from atan2 is in [-pi, pi] and the carrier correction uses
       four blocks of spacing. The extra padding covers frequency rounding
       at the released search range endpoints. */
    const double edge = tau / 8. + 0x1p-40;
    const double step = 2. * edge / intervals;
    double largest = 0., curvature = 0.;
    for (int g = 0; g <= intervals; ++g) {
        double value = cr[0], theta = -edge + g * step;
        for (int d = 1; d < blocks; ++d)
            value += 2. * (cr[d] * cos(d * theta) + ci[d] * sin(d * theta));
        largest = fmax(largest, value);
    }
    for (int d = 1; d < blocks; ++d)
        curvature += 2. * d*d * hypot(cr[d], ci[d]);

    double denominator = fmax(power * energy, 1e-15);
    double pad = allowance * absolute + 0x1p-900;
    *triangle = nextafter((broad + pad) / denominator, INFINITY);
    *restricted = nextafter((fmin(broad, largest + curvature * step*step/8.) + pad)
                            / denominator, INFINITY);
    if (!isfinite(*triangle) || !isfinite(*restricted) || !isfinite(power * energy))
        *triangle = *restricted = INFINITY;
}

__attribute__((target("avx2")))
int receiver_refine_enclosure(const float *x, const float *h, RefineRequest request,
                              double lo, double hi, double out[4], double upper[4])
{
    if (!safe_request(request) || !__builtin_cpu_supports("avx2"))
        return 0;
    RefineRotation prepared;
    const RefineRotation *rotations[1] = {&prepared};
    BlockMatrix matrix;
    prepare_refine_rotation(h, request.hz, &prepared);
    correlate_group(x, rotations, 1, request.epoch, &matrix);
    finish_refine(request.epoch, request.hz, lo, hi, prepared.energy, matrix, out);
    for (int parity = 0; parity < 2; ++parity) {
        upper[2*parity] = upper[2*parity+1] = 0.;
        for (int i = 0; i < 9; ++i) {
            double triangle, restricted;
            enclose_offset(matrix, i, parity, prepared.energy, &triangle, &restricted);
            upper[2*parity] = fmax(upper[2*parity], triangle);
            upper[2*parity+1] = fmax(upper[2*parity+1], restricted);
        }
    }
    return 1;
}
