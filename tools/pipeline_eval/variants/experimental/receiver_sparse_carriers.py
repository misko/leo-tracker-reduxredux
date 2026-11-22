"""Avoid building powers for ineligible bins and reuse their block winners."""

from .receiver_build import replace


def overlay(source):
    source = replace(source, '#include "receiver_spectral_vectors.inc"',
                     '#include "receiver_spectral_vectors.inc"\n#include "receiver_sparse_carriers.inc"')
    source = replace(source, "    const int eligible_count = cache->count;",
                     "    const int eligible_count = cache->count;\n"
                     "    if (!eligible_count) return 0;\n"
                     "    SparseCarrierSweep sweep;\n"
                     "    const int sparse = packed && sparse_carrier_setup(&sweep, eligible, eligible_count);")
    source = replace(source, "        memset(w->power, 0, bins * sizeof(double));",
                     "        if (!sparse) memset(w->power, 0, bins * sizeof(double));")
    source = replace(source, "                spectral_carrier_power(w->power, w->scratch, bins);",
                     "                if (sparse) sparse_carrier_power(&sweep, w->power, w->scratch, m == 0);\n"
                     "                else spectral_carrier_power(w->power, w->scratch, bins);")
    return replace(source, "        int prev = -1;",
                   """        if (sparse) {
            int selected[2];
            sparse_carrier_peaks(&sweep, w->power, minimum_gap, selected);
            for (int entry = 0; entry < 2 && selected[entry] >= 0; ++entry) {
                int best = selected[entry];
                all[used++] = (Seed){w->power[best] / fmax(energy, 1e-15), epochs[i] * w->stride, best};
            }
            continue;
        }
        int prev = -1;""")
