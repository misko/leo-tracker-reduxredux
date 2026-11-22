/* Two ordinary maps followed by bounded SQUAREM acceleration of log rates. */
static uint64_t accel_attempted,accel_rejected;

void nb_accel_counts(uint64_t *counts) {
    counts[0]=accel_attempted;
    counts[1]=accel_rejected;
}

static int extrapolate_rates(int k,int t,const double *rate,const double *prate,
                             const double *next,const double *pnext,const double *first,
                             double beta0,double pb0,double *proposal) {
    double length=0.,curvature=0.;
    for (int j=0;j<k+t;j++) {
        double following=j<k ? log(next[j]/rate[j]) : log(pnext[j-k]/prate[j-k]);
        double change=following-first[j];
        proposal[j]=change;
        length+=first[j]*first[j];
        curvature+=change*change;
    }
    if (!(curvature>0.)) return 0;
    double jump=fmin(4.,sqrt(length/curvature));
    if (!(jump>1.)) return 0;
    for (int j=0;j<k+t;j++) {
        double following=j<k ? next[j] : pnext[j-k];
        double floor=j<k ? beta0 : pb0;
        double offset=2.*(jump-1.)*first[j]+(jump*jump-1.)*proposal[j];
        proposal[j]=following*exp(offset);
        if (!isfinite(proposal[j]) || proposal[j]<floor) return 0;
    }
    return 1;
}
