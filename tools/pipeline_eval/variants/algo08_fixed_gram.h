/* Caches numeric track Gram entries only while every contributing row agrees. */
#include <stdatomic.h>
#include <time.h>

enum gram_counter {
    gram_calls, gram_cpu_ns, gram_cold, gram_reused, gram_fallback,
    original_products, replayed_products, reused_group_columns,
    assembly_calls, assembly_cpu_ns, assembly_mapped, gram_counters
};
static _Atomic uint64_t gram_counts[gram_counters];
static _Atomic int gram_reuse_enabled;

struct GramReuse {
    double *storage, *input, *normalized, *noise, *matrix;
    int *indices, *changed, *dirty_count;
    atomic_flag busy;
    int valid;
};

static uint64_t gram_clock(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &now)) return 0;
    return (uint64_t)now.tv_sec * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
}

void nb_configure_fixed_gram(int enabled) {
    atomic_store_explicit(&gram_reuse_enabled, enabled, memory_order_relaxed);
}

void nb_fixed_gram_counts(uint64_t *output) {
    for (int i = 0; i < gram_counters; ++i)
        output[i] = atomic_load_explicit(&gram_counts[i], memory_order_relaxed);
}

static void gram_free(struct GramReuse *cache) {
    if (!cache) return;
    free(cache->storage);
    free(cache->indices);
    free(cache);
}

static struct GramReuse *gram_allocate(const Layout *l, const int64_t *groups) {
    if (atomic_load_explicit(&gram_reuse_enabled, memory_order_relaxed) != 1 || !l->total)
        return NULL;
    size_t cells = 0;
    for (int i = 0; i < l->n; ++i) {
        int g = (int)groups[i];
        cells += l->offset[g + 1] - l->offset[g];
    }
    size_t doubles = 2 * cells + l->n + l->mats;
    if (doubles > (8 * 1024 * 1024) / sizeof(double)) return NULL;
    struct GramReuse *cache = calloc(1, sizeof(*cache));
    if (!cache) return NULL;
    cache->storage = malloc(doubles * sizeof(double));
    cache->indices = malloc(((size_t)2 * l->total + l->k) * sizeof(int));
    if (!cache->storage || !cache->indices) {
        gram_free(cache);
        return NULL;
    }
    cache->input = cache->storage;
    cache->normalized = cache->input + cells;
    cache->noise = cache->normalized + cells;
    cache->matrix = cache->noise + l->n;
    cache->changed = cache->indices + l->total;
    cache->dirty_count = cache->changed + l->total;
    atomic_flag_clear(&cache->busy);
    return cache;
}

struct Accumulate {
    int source, target;
};

struct PosteriorMap {
    struct Accumulate *cells;
    int *ranges;
};

static void posterior_free(struct PosteriorMap *map) {
    if (!map) return;
    free(map->cells);
    free(map->ranges);
    free(map);
}

static struct PosteriorMap *posterior_map(const Layout *l) {
    if (atomic_load_explicit(&gram_reuse_enabled, memory_order_relaxed) != 2 || !l->mats)
        return NULL;
    if ((size_t)l->mats * sizeof(struct Accumulate) + 4 * l->k * sizeof(int) > 8 * 1024 * 1024)
        return NULL;
    struct PosteriorMap *map = malloc(sizeof(*map));
    if (!map) return NULL;
    map->cells = malloc((size_t)l->mats * sizeof(*map->cells));
    map->ranges = malloc((size_t)4 * l->k * sizeof(*map->ranges));
    if (!map->cells || !map->ranges) {
        posterior_free(map);
        return NULL;
    }

    int index = 0, s = l->s, stride = s ? s : 1;
    for (int g = 0; g < l->k; ++g) {
        int off = l->offset[g], q = l->offset[g + 1] - off;
        for (int kind = 0; kind < 3; ++kind) {
            map->ranges[4 * g + kind] = index;
            for (int j = 0; j < q; ++j) {
                int column = l->columns[off + j];
                int sj = l->shared[column], dj = l->private_index[column];
                for (int h = 0; h < q; ++h) {
                    int other = l->columns[off + h];
                    int sh = l->shared[other], dh = l->private_index[other], target;
                    if (kind == 0 && sh >= 0 && sj >= sh)
                        target = sh * s + sj;
                    else if (kind == 1 && sj >= 0 && sh < 0)
                        target = (2 * g + dh) * stride + sj;
                    else if (kind == 2 && sj < 0 && sh < 0)
                        target = 4 * g + 2 * dj + dh;
                    else continue;
                    map->cells[index++] = (struct Accumulate){l->matrix_offset[g] + j*q+h, target};
                }
            }
        }
        map->ranges[4 * g + 3] = index;
    }
    return map;
}

static void assemble_posterior(const Layout *l, const double *matrix, const double *rhs,
                               const double *power, const double *weight,
                               const double *precision, double *a, double *e, double *d,
                               double *bg, double *b) {
    const struct PosteriorMap *map = l->posterior;
    for (int g = 0; g < l->k; ++g) {
        double w = power[g] * weight[g];
        int nd = l->width[g];
        for (int j = 0; j < nd; ++j) d[4*g + 3*j] = precision[l->private_cols[2*g + j]];
        for (int j = l->offset[g]; j < l->offset[g + 1]; ++j) {
            int column = l->columns[j], shared = l->shared[column];
            if (shared >= 0) bg[shared] += w * rhs[j];
            else b[2*g + l->private_index[column]] += w * rhs[j];
        }
        double *destinations[] = {a, e, d};
        for (int kind = 0; kind < 3; ++kind) {
            const struct Accumulate *start = map->cells + map->ranges[4*g + kind];
            const struct Accumulate *stop = map->cells + map->ranges[4*g + kind + 1];
            double *destination = destinations[kind];
            for (const struct Accumulate *cell = start; cell < stop; ++cell)
                destination[cell->target] += w * matrix[cell->source];
        }
    }
    /* Every mirrored cell previously accumulated the same products in the
       same order. Later Schur operations keep their original two triangles. */
    for (int j = 0; j < l->s; ++j)
        for (int h = 0; h < j; ++h) a[j*l->s + h] = a[h*l->s + j];
}

static int cache_gram(Layout *l, const double *y, const double *u, const double *sigma,
                      const int64_t *groups, double *matrix, double *rhs) {
    struct GramReuse *cache = l->gram_reuse;
    if (!cache || atomic_flag_test_and_set(&cache->busy)) return 0;
    int valid = cache->valid;
    memset(cache->changed, 0, (size_t)l->total * sizeof(int));
    size_t cursor = 0;
    for (int i = 0; i < l->n; ++i) {
        int g = (int)groups[i], off = l->offset[g], q = l->offset[g + 1] - off;
        int same_noise = valid && !memcmp(sigma + i, cache->noise + i, sizeof(double));
        if (!same_noise) cache->noise[i] = sigma[i];
        double response = y[i] / sigma[i];
        for (int j = 0; j < q; ++j, ++cursor) {
            const double *source = u + (size_t)i * l->p + l->columns[off + j];
            if (!same_noise || memcmp(source, cache->input + cursor, sizeof(double))) {
                double normalized = *source / sigma[i];
                if (!isfinite(normalized) || fabs(normalized) > 0x1p100) {
                    memset(rhs, 0, (size_t)l->total * sizeof(double));
                    cache->valid = 0;
                    atomic_flag_clear(&cache->busy);
                    return 0;
                }
                cache->input[cursor] = *source;
                cache->normalized[cursor] = normalized;
                cache->changed[off + j] = 1;
            }
            rhs[off + j] += cache->normalized[cursor] * response;
        }
    }

    if (valid) memcpy(matrix, cache->matrix, (size_t)l->mats * sizeof(double));
    uint64_t unchanged = 0, original = 0, replayed = 0;
    for (int g = 0; g < l->k; ++g) {
        int off = l->offset[g], q = l->offset[g + 1] - off, dirty = 0;
        double *block = matrix + l->matrix_offset[g];
        for (int j = 0; j < q; ++j) {
            if (cache->changed[off + j]) {
                cache->indices[off + dirty++] = j;
                memset(block + j * q, 0, (size_t)q * sizeof(double));
            }
        }
        cache->dirty_count[g] = dirty;
        unchanged += q - dirty;
    }
    cursor = 0;
    for (int i = 0; i < l->n; ++i) {
        int g = (int)groups[i], off = l->offset[g], q = l->offset[g + 1] - off;
        int *indices = cache->indices + off, dirty = cache->dirty_count[g];
        const double *row = cache->normalized + cursor;
        double *block = matrix + l->matrix_offset[g];
        for (int c = 0; c < dirty; ++c) {
            int j = indices[c];
            for (int h = 0; h < q; ++h) block[j * q + h] += row[j] * row[h];
        }
        original += (uint64_t)q * q;
        replayed += (uint64_t)dirty * q;
        cursor += q;
    }
    /* A reflected product has the same operands and original observation order. */
    for (int g = 0; g < l->k; ++g) {
        int off = l->offset[g], q = l->offset[g + 1] - off;
        int *indices = cache->indices + off, dirty = cache->dirty_count[g];
        double *block = matrix + l->matrix_offset[g];
        for (int c = 0; c < dirty; ++c) {
            int j = indices[c];
            for (int h = 0; h < q; ++h)
                if (!cache->changed[off + h]) block[h * q + j] = block[j * q + h];
        }
    }
    memcpy(cache->matrix, matrix, (size_t)l->mats * sizeof(double));
    cache->valid = 1;
    ++gram_counts[valid ? gram_reused : gram_cold];
    gram_counts[original_products] += original;
    gram_counts[replayed_products] += replayed;
    gram_counts[reused_group_columns] += unchanged;
    atomic_flag_clear(&cache->busy);
    return 1;
}
