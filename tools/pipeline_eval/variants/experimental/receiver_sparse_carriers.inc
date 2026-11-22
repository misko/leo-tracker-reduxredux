/* Compute only existing eligible powers and share block maxima between the two picks. */

enum { carrier_tile = 32, carrier_runs = 2, carrier_tiles = bins / carrier_tile + carrier_runs };
typedef struct { int begin, end; } CarrierRun;
typedef struct { CarrierRun span; int peak; } CarrierTile;
typedef struct {
    CarrierRun run[carrier_runs];
    CarrierTile tile[carrier_tiles];
    int runs, tiles;
} SparseCarrierSweep;

static int sparse_carrier_setup(SparseCarrierSweep *sweep, const uint16_t *eligible, int count) {
    /* The existing eligibility builder writes sorted, unique bin indices.
       Their index minus position is constant on each contiguous run. */
    sweep->runs = sweep->tiles = 0;
    for (int start = 0; start < count;) {
        if (sweep->runs == carrier_runs) return 0;
        const int offset = eligible[start] - start;
        int left = start + 1, right = count;
        while (left < right) {
            int middle = left + (right - left) / 2;
            if (eligible[middle] - middle == offset)
                left = middle + 1;
            else
                right = middle;
        }
        CarrierRun run = {eligible[start], eligible[left - 1] + 1};
        sweep->run[sweep->runs++] = run;
        for (int begin = run.begin; begin < run.end; begin += carrier_tile) {
            int end = begin + carrier_tile;
            if (end > run.end) end = run.end;
            sweep->tile[sweep->tiles++] = (CarrierTile){{begin, end}, -1};
        }
        start = left;
    }
    return 1;
}

__attribute__((target("avx2")))
static inline double carrier_maximum(__m256d values) {
    __m128d x = _mm_max_pd(_mm256_castpd256_pd128(values), _mm256_extractf128_pd(values, 1));
    return _mm_cvtsd_f64(_mm_max_sd(x, _mm_unpackhi_pd(x, x)));
}

__attribute__((target("avx2")))
static inline int first_carrier_equal(const double *powers, CarrierRun run, double wanted) {
    __m256d threshold = _mm256_set1_pd(wanted);
    int i = run.begin;
    for (; i + 3 < run.end; i += 4) {
        __m256d matches = _mm256_cmp_pd(_mm256_loadu_pd(powers + i), threshold, _CMP_EQ_OQ);
        unsigned mask = _mm256_movemask_pd(matches);
        if (mask) return i + __builtin_ctz(mask);
    }
    for (; i < run.end; ++i)
        if (powers[i] == wanted) return i;
    return -1;
}

__attribute__((target("avx2")))
static int carrier_interval_max(const double *powers, CarrierRun run) {
    __m256d best = _mm256_set1_pd(-INFINITY);
    int i = run.begin;
    for (; i + 3 < run.end; i += 4)
        best = _mm256_max_pd(_mm256_loadu_pd(powers + i), best);
    double peak = carrier_maximum(best);
    for (; i < run.end; ++i)
        if (powers[i] > peak) peak = powers[i];
    return first_carrier_equal(powers, run, peak);
}

__attribute__((target("avx2")))
static void sparse_carrier_power(SparseCarrierSweep *sweep, double *powers, const Sample *fft,
                                 int first_mode) {
    if (first_mode) {
        for (int k = 0; k < sweep->runs; ++k) {
            CarrierRun run = sweep->run[k];
            int i = run.begin;
            for (; i + 3 < run.end; i += 4) {
                __m256d values = _mm256_cvtps_pd(spectral_power(spectral_samples(fft + i)));
                _mm256_storeu_pd(powers + i, _mm256_add_pd(_mm256_setzero_pd(), values));
            }
            for (; i < run.end; ++i)
                powers[i] = 0. + power(fft[i]);
        }
        return;
    }
    for (int k = 0; k < sweep->tiles; ++k) {
        CarrierTile *tile = &sweep->tile[k];
        __m256d best = _mm256_set1_pd(-INFINITY);
        int i = tile->span.begin;
        for (; i + 3 < tile->span.end; i += 4) {
            __m256d values = _mm256_cvtps_pd(spectral_power(spectral_samples(fft + i)));
            values = _mm256_add_pd(_mm256_loadu_pd(powers + i), values);
            _mm256_storeu_pd(powers + i, values);
            /* MAXPD returns its second operand for an unordered comparison. */
            best = _mm256_max_pd(values, best);
        }
        double peak = carrier_maximum(best);
        for (; i < tile->span.end; ++i) {
            powers[i] += power(fft[i]);
            if (powers[i] > peak) peak = powers[i];
        }
        tile->peak = first_carrier_equal(powers, tile->span, peak);
    }
}

static inline void carrier_consider(const double *powers, int trial, int *best) {
    if (trial >= 0 && (*best < 0 || powers[trial] > powers[*best]))
        *best = trial;
}

static inline CarrierRun carrier_intersection(CarrierRun a, CarrierRun b) {
    return (CarrierRun){a.begin > b.begin ? a.begin : b.begin, a.end < b.end ? a.end : b.end};
}

static void sparse_carrier_peaks(const SparseCarrierSweep *sweep, const double *powers, int gap,
                                 int best[2]) {
    best[0] = best[1] = -1;
    if (!sweep->runs) return;
    int first = sweep->run[0].begin;
    if (isnan(powers[first]))
        best[0] = first;
    else
        for (int k = 0; k < sweep->tiles; ++k)
            carrier_consider(powers, sweep->tile[k].peak, &best[0]);
    if (gap <= 0) {
        best[1] = best[0];
        return;
    }
    if (gap > bins / 2) return;
    /* Allowed bins form one circular arc. Process its split in ascending
       absolute bin order to retain the original tie and NaN behavior. */
    int start = (best[0] + gap) % bins, end = start + bins - 2 * gap + 1;
    CarrierRun allowed[2];
    int count = 1;
    if (end > bins) {
        allowed[0] = (CarrierRun){0, end - bins};
        allowed[count++] = (CarrierRun){start, bins};
    } else {
        allowed[0] = (CarrierRun){start, end};
    }
    for (int k = 0; k < sweep->runs && best[1] < 0; ++k) {
        for (int i = 0; i < count; ++i) {
            CarrierRun span = carrier_intersection(sweep->run[k], allowed[i]);
            if (span.begin < span.end) {
                best[1] = span.begin;
                break;
            }
        }
    }
    if (best[1] < 0 || isnan(powers[best[1]])) return;
    for (int k = 0; k < sweep->tiles; ++k) {
        const CarrierTile *tile = &sweep->tile[k];
        if (tile->peak < 0) continue;
        int distance = abs(tile->peak - best[0]);
        if (distance >= gap && bins - distance >= gap) {
            carrier_consider(powers, tile->peak, &best[1]);
        } else {
            for (int i = 0; i < count; ++i) {
                CarrierRun span = carrier_intersection(tile->span, allowed[i]);
                if (span.begin < span.end)
                    carrier_consider(powers, carrier_interval_max(powers, span), &best[1]);
            }
        }
    }
}
