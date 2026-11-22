"""Pack the two-mode scout mathematics around each unchanged FFT plan."""

from .receiver_build import replace


def overlay(source):
    source = replace(source, "static void find_times(TimingFirst *w, int *epochs) {",
                     '#include "receiver_spectral_vectors.inc"\n\n'
                     "static void find_times(TimingFirst *w, int *epochs) {\n"
                     '    const int packed = __builtin_cpu_supports("avx2");')
    start = source.index("        memset(w->scratch, 0,", source.index("static void find_times("))
    end = source.index("\n    }\n", start)
    reference = source[start:end].splitlines(keepends=True)
    source = source[:start] + """
        if (packed) {
            spectral_lag_products(w->scratch, w->prefix, w->modes, w->modes + w->width,
                                  w->width, lag, w->correlation_size);
            transform(w, w->correlation_size, 0);
            spectral_filter(w->scratch, w->filters + k * w->correlation_size, w->correlation_size);
            fftwf_execute(w->plans[timing_backward]);
            spectral_timing_scores(w->time_score, w->prefix, w->scratch, w->epochs, len,
                                   w->correlation_size);
        } else {
""" + "".join("    " + line for line in reference) + "\n        }" + source[end:]
    source = replace(source, "    int used = 0, len = 64 * symbol / w->stride;",
                     '    const int packed = __builtin_cpu_supports("avx2");\n'
                     "    int used = 0, len = 64 * symbol / w->stride;")
    return replace(source, """            memset(w->scratch, 0, bins * sizeof(Sample));
            for (int j = 0; j < len; ++j) {
                w->scratch[j] = multiply(v[j], conjugate(w->code[j]));
                energy += power(v[j]);
            }
            transform(w, bins, 0);
            for (int j = 0; j < bins; ++j)
                w->power[j] += power(w->scratch[j]);""",
                   """            if (packed) {
                energy = spectral_carrier_input(w->scratch, v, w->code, len, bins, energy);
                transform(w, bins, 0);
                spectral_carrier_power(w->power, w->scratch, bins);
            } else {
                memset(w->scratch, 0, bins * sizeof(Sample));
                for (int j = 0; j < len; ++j) {
                    w->scratch[j] = multiply(v[j], conjugate(w->code[j]));
                    energy += power(v[j]);
                }
                transform(w, bins, 0);
                for (int j = 0; j < bins; ++j)
                    w->power[j] += power(w->scratch[j]);
            }""")
