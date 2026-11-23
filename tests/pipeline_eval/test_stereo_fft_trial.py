import struct

from reports.ALGO08.v3.stereo_fft_trial import exact_helpers, factor_bytes


def test_batched_helpers_inherit_native_tie_and_gate_code():
    stock = """static void find_times(TimingFirst *w, int *epochs) {
    int radius = (int)nearbyint(6. / w->stride);
    epochs[0] = radius;
}

static double bin_hz(const TimingFirst *w, int i) { return i; }
static int find_carriers() {
    for (int i = 0; i < 2; ++i) {
        int prev = -1;
        indices[used++] = epochs[i];
    }
    return used;
}
static int detect_lane() {
    Peak peaks[max_peaks];
    if (gate(w, peaks, 0, 1)) return 1;
    return 0;
}

int timing_first_detect() { return 0; }
"""
    output = exact_helpers(stock)
    assert output.startswith(stock)
    assert output.count("    epochs[0] = radius;") == 2
    assert output.count("indices[used++] = epochs[i];") == 1
    assert output.count("indices[used++] = epoch;") == 1
    assert output.count("if (gate(w, peaks, 0, 1)) return 1;") == 2


def test_factor_bytes_keep_order_and_signed_fft_result():
    factors = ((0, 17, -.125, -3000., .975, .75), (1, 100, 0., 3., .9, .7))
    actual = factor_bytes(factors)
    assert len(actual) == 80
    assert tuple(struct.iter_unpack("=ii4d", actual)) == factors
    assert factor_bytes(factors[::-1]) != actual
