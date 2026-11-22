/* Added to an isolated copy of the qualified grouped bound. */
#include <float.h>

static _Thread_local uint64_t bstats_calls, bstats_fallbacks, bstats_rows_avoided, bstats_groups;

void group_statistics_counts(uint64_t *out) {
    out[0]=bstats_calls;
    out[1]=bstats_fallbacks;
    out[2]=bstats_rows_avoided;
    out[3]=bstats_groups;
}

static int group_energy(const Layout *layout, const double *gram, const double *shift_rhs,
    const double *yy, const double *counts, const double *anchor, const double *mean,
    double *shift_mean, double *energy, double *replay) {
    int failed=0;
    for (int g=0;g<layout->k;g++) {
        int off=layout->offset[g],q=layout->offset[g+1]-off;
        const int *columns=layout->columns+off;
        const double *block=gram+layout->matrix_offset[g];
        int pivot=layout->width[g] ? layout->private_cols[2*g] : -1;
        for (int j=0;j<q;j++)
            shift_mean[j]=mean[columns[j]]-(columns[j]==pivot ? anchor[g] : 0.);
        double sum=yy[g], magnitude=yy[g];
        for (int j=0;j<q;j++) {
            double mu=shift_mean[j], dot=0., dot_magnitude=0.;
            for (int h=0;h<q;h++) {
                double term=block[j*q+h]*shift_mean[h];
                dot+=term;
                dot_magnitude+=fabs(term);
            }
            sum+=mu*(dot-2.*shift_rhs[off+j]);
            magnitude+=fabs(mu)*(dot_magnitude+2.*fabs(shift_rhs[off+j]));
        }
        /* Preserve the original row operation in cancellation-sensitive groups. */
        double uncertainty=16.*DBL_EPSILON*(counts[g]+q+3.)*magnitude;
        int invalid=!isfinite(sum) || !isfinite(uncertainty) || sum<0.
            || uncertainty>2e-7*(1.+sum);
        replay[g]=invalid;
        energy[g]=invalid ? 0. : sum;
        failed+=invalid;
        if (!invalid) bstats_rows_avoided+=(uint64_t)counts[g];
    }
    bstats_groups+=layout->k;
    bstats_fallbacks+=failed;
    return failed;
}
