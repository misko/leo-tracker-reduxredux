#include <float.h>

static _Thread_local uint64_t conditioning_counts[3];

void nb_conditioning_counts(uint64_t out[3]) {
    memcpy(out, conditioning_counts, sizeof(conditioning_counts));
}

/* Column-major lower factor. The forward comparison solve majorizes the
 * elementwise absolute inverse applied to an all-ones vector. */
double nb_schur_reciprocal_floor(int n, const double *root, double gram_norm) {
    if (n < 1 || n > 512 || !(gram_norm > 0.) || !isfinite(gram_norm)) return 0.;
    double upper[512], frobenius_squared=0.;
    const double pad=1.+8.*DBL_EPSILON*(n+3);
    for (int i=0; i<n; ++i) upper[i]=1.;
    for (int j=0; j<n; ++j) {
        const double *column=root+(size_t)j*n;
        const double diagonal=column[j];
        if (!(diagonal > 0.) || !isfinite(diagonal)) return 0.;
        double row=(upper[j]/diagonal)*pad;
        frobenius_squared+=row*row;
        for (int i=j+1; i<n; ++i) upper[i]+=fabs(column[i])*row;
    }
    double condition=gram_norm*sqrt((double)n)*frobenius_squared*pad;
    return condition > 0. && isfinite(condition) ? 1./condition : 0.;
}

static int schur_condition(pocon_fn pocon, int n, const double *root,
                           double norm, double min_rcond) {
    ++conditioning_counts[0];
#ifdef LEO_CONDITION_CERT
    if (isfinite(min_rcond) && min_rcond > 0. &&
        nb_schur_reciprocal_floor(n, root, norm) > 8.*min_rcond) {
        ++conditioning_counts[1];
        return 0;
    }
#endif
    double rcond=0.;
    int reject=pocon(102,'L',n,root,n,norm,&rcond) || !isfinite(rcond) || rcond < min_rcond;
    conditioning_counts[2]+=reject;
    return reject;
}
