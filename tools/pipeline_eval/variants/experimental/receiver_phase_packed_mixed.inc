/* The frame-relative references already include the phase rotation. Reuse
   the packed interpolation and the original four symbol sum chains. */
__attribute__((target("avx2,fma")))
static void correlate_mixed_packed(
    const IqSample *restrict iq, const int32_t *restrict starts,
    const int32_t *restrict row, const double *restrict weights,
    const complex64x2 *restrict exact, const complex64x2 *restrict control,
    complex64x2 *restrict exact_out, complex64x2 *restrict control_out)
{
    for (int s = 0; s < symbols; ++s) {
        int offset = s * taps;
        FractionalPairs sample = fractional_samples(iq, starts + offset, row + offset, weights);
        FractionalPairs a = fractional_terms(sample, exact + offset);
        FractionalPairs b = fractional_terms(sample, control + offset);
        for (int t = lanes; t < taps; t += lanes) {
            int index = offset + t;
            sample = fractional_samples(iq, starts + index, row + index, weights);
            a = fractional_add(a, fractional_terms(sample, exact + index));
            b = fractional_add(b, fractional_terms(sample, control + index));
        }
        finish_fractional(a, exact_out + s);
        finish_fractional(b, control_out + s);
    }
}

void correlated_fractional_mixed(
    const IqSample *restrict iq, const int32_t *restrict starts,
    const int32_t *restrict row, const double *restrict weights,
    const complex64x2 *restrict exact, const complex64x2 *restrict control,
    complex64x2 *restrict exact_out, complex64x2 *restrict control_out)
{
    if (__builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma"))
        correlate_mixed_packed(iq, starts, row, weights, exact, control, exact_out, control_out);
    else
        correlated_fractional_mixed_reference(iq, starts, row, weights, exact, control,
                                              exact_out, control_out);
}
