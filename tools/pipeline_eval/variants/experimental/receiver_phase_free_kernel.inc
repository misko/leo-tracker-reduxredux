void correlated_fractional_mixed(
    const IqSample *restrict iq, const int32_t *restrict starts,
    const int32_t *restrict weight_row, const double *restrict weights,
    const complex64x2 *restrict exact, const complex64x2 *restrict control,
    complex64x2 *restrict exact_out, complex64x2 *restrict control_out)
{
    for (int s = 0; s < symbols; ++s) {
        complex64x2 exact_lanes[lanes], control_lanes[lanes];
        int offset = s * taps;
        for (int t = 0; t < taps; ++t) {
            int index = offset + t;
            complex64x2 sample = interpolate(iq + starts[index],
                weights + weight_row[index] * lanczos_taps);
            accumulate(sample, exact + offset, control + offset, t, exact_lanes, control_lanes);
        }
        exact_out[s] = pairwise_sum(exact_lanes);
        control_out[s] = pairwise_sum(control_lanes);
    }
}
