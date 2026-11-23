#include <immintrin.h>

int nb_batch_width(const Layout *l) {
    return l ? (l->mats ? l->mats : 1) + l->total : 0;
}

/* Each vector lane is a separate location. Its reductions retain row order. */
__attribute__((target("avx2")))
int nb_prepare_four(const Layout *l, const double *const y[4], const double *const u[4],
                    const double *sigma, const int64_t *groups, double *out) {
    int width=nb_batch_width(l);
    if (!width) return NB_UNSUPPORTED;
    int matrix_width=width-l->total;
    __m256d *stats=aligned_alloc(32, (size_t)width*sizeof(*stats));
    if (!stats) return NB_MEMORY;
    memset(stats, 0, (size_t)width*sizeof(*stats));
    for (int i=0; i<l->n; ++i) {
        int g=(int)groups[i], off=l->offset[g], q=l->offset[g+1]-off;
        __m256d scale=_mm256_set1_pd(sigma[i]);
        __m256d response=_mm256_div_pd(_mm256_setr_pd(y[0][i],y[1][i],y[2][i],y[3][i]),scale);
        __m256d row[512];
        for (int j=0; j<q; ++j) {
            size_t z=(size_t)i*l->p+l->columns[off+j];
            row[j]=_mm256_div_pd(_mm256_setr_pd(u[0][z],u[1][z],u[2][z],u[3][z]),scale);
        }
        __m256d *matrix=stats+l->matrix_offset[g];
        __m256d *rhs=stats+matrix_width+off;
        for (int j=0; j<q; ++j) {
            rhs[j]=_mm256_add_pd(rhs[j],_mm256_mul_pd(row[j],response));
            for (int h=0; h<=j; ++h)
                matrix[j*q+h]=_mm256_add_pd(matrix[j*q+h],_mm256_mul_pd(row[j],row[h]));
        }
    }
    for (int g=0; g<l->k; ++g) {
        int q=l->offset[g+1]-l->offset[g];
        __m256d *matrix=stats+l->matrix_offset[g];
        for (int j=0; j<q; ++j)
            for (int h=0; h<j; ++h) matrix[h*q+j]=matrix[j*q+h];
    }
    for (int i=0; i<width; ++i) {
        double values[4];
        _mm256_storeu_pd(values,stats[i]);
        for (int lane=0; lane<4; ++lane) out[lane*width+i]=values[lane];
    }
    free(stats);
    return NB_OK;
}
