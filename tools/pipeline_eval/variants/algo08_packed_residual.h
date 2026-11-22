/* Pack eight consecutive observations from one group for independent dot products. */
#define NB_ROW_LANES 8
typedef struct {
    int start;
    size_t offset;
} ResidualBlock;

typedef struct {
    ResidualBlock *blocks;
    double *values;
    int count;
} ResidualRows;

/* Only this independent row recurrence needs a vector instruction set. */
#if (defined(__x86_64__) || defined(__i386__)) && defined(__GNUC__)
__attribute__((target("avx2")))
#endif
static void packed_dot(const Layout *l, const double *values, const double *mean,
                       int begin, int end, double *restrict predicted) {
    for (int z = begin; z < end; z++, values += NB_ROW_LANES) {
        double m = mean[l->columns[z]];
        for (int lane = 0; lane < NB_ROW_LANES; lane++)
            predicted[lane] += values[lane] * m;
    }
}

static ResidualRows prepare_residual_rows(const Layout *l, const int64_t *groups,
                                          const double *u) {
    ResidualRows rows = {0};
#if (defined(__x86_64__) || defined(__i386__)) && defined(__GNUC__)
    if (!__builtin_cpu_supports("avx2")) return rows;
#endif
    int count = 0;
    size_t total = 0;
    for (int first = 0; first < l->n;) {
        int g = (int)groups[first], end = first + 1;
        while (end < l->n && groups[end] == g) end++;
        int blocks = (end - first) / NB_ROW_LANES;
        count += blocks;
        total += (size_t)blocks * NB_ROW_LANES * (l->offset[g + 1] - l->offset[g]);
        first = end;
    }
    if (!total || total > 1048576 || count * NB_ROW_LANES < l->n / 2) return rows;
    rows.blocks = malloc((size_t)count * sizeof(*rows.blocks));
    rows.values = malloc(total * sizeof(*rows.values));
    if (!rows.blocks || !rows.values) {
        free(rows.blocks);
        free(rows.values);
        return (ResidualRows){0};
    }
    size_t cursor = 0;
    for (int first = 0; first < l->n;) {
        int g = (int)groups[first], end = first + 1;
        while (end < l->n && groups[end] == g) end++;
        int begin = l->offset[g], stop = l->offset[g + 1];
        for (int i = first; i + NB_ROW_LANES <= end; i += NB_ROW_LANES) {
            rows.blocks[rows.count++] = (ResidualBlock){i, cursor};
            for (int z = begin; z < stop; z++) {
                int j = l->columns[z];
                for (int lane = 0; lane < NB_ROW_LANES; lane++)
                    rows.values[cursor++] = u[(size_t)(i + lane) * l->p + j];
            }
        }
        first = end;
    }
    return rows;
}

static int residual_energy(const Layout *l, const ResidualRows *rows, const int64_t *groups,
                           const double *y, const double *u, const double *sigma,
                           const double *mean, double *native, double *energy) {
    int block = 0;
    for (int i = 0; i < l->n;) {
        int g = (int)groups[i], begin = l->offset[g], end = l->offset[g + 1];
        if (block < rows->count && i == rows->blocks[block].start) {
            const double *values = rows->values + rows->blocks[block++].offset;
            double predicted[NB_ROW_LANES] = {0};
            packed_dot(l, values, mean, begin, end, predicted);
            for (int lane = 0; lane < NB_ROW_LANES; lane++, i++) {
                native[i] = y[i] - predicted[lane];
                double r = native[i] / sigma[i];
                energy[g] += r * r;
                if (!isfinite(native[i])) return NB_NONFINITE;
            }
        } else {
            double val = 0.;
            for (int z = begin; z < end; z++) {
                int j = l->columns[z];
                val += u[(size_t)i * l->p + j] * mean[j];
            }
            native[i] = y[i] - val;
            double r = native[i] / sigma[i];
            energy[g] += r * r;
            if (!isfinite(native[i])) return NB_NONFINITE;
            i++;
        }
    }
    return NB_OK;
}
