/* Export a lower Cholesky in private-then-shared column order. */
static int export_posterior(const Layout *l, const double *d, const double *e,
                            const double *root, const double *prior,
                            double *lower, int32_t *order) {
    const int p=l->p, s=l->s, begin=p-s, stride=s?s:1;
    int next=0;
    memset(lower,0,(size_t)p*p*sizeof(double));
    for (int g=0;g<l->k;g++) {
        int width=l->width[g];
        if (!width) continue;
        const double *block=d+4*g;
        double a=sqrt(block[0]), b=0., c=0.;
        if (!isfinite(a) || a<=0.) return 0;
        lower[(size_t)next*p+next]=a;
        order[next]=l->private_cols[2*g];
        if (width==2) {
            b=block[2]/a;
            c=sqrt(block[3]-b*b);
            if (!isfinite(c) || c<=0.) return 0;
            lower[(size_t)(next+1)*p+next]=b;
            lower[(size_t)(next+1)*p+next+1]=c;
            order[next+1]=l->private_cols[2*g+1];
        }
        const double *first=e+(size_t)(2*g)*stride;
        const double *second=first+stride;
        for (int j=0;j<s;j++) {
            double *row=lower+(size_t)(begin+j)*p;
            row[next]=first[j]/a;
            if (width==2) row[next+1]=(second[j]-row[next]*b)/c;
        }
        next+=width;
    }
    for (int j=0;j<p;j++) {
        int shared=l->shared[j];
        if (shared>=0) order[begin+shared]=j;
        else if (l->private_index[j]<0) {
            order[next]=j;
            lower[(size_t)next*p+next]=sqrt(prior[j]);
            next++;
        }
    }
    if (next!=begin) return 0;
    for (int j=0;j<s;j++) for (int k=0;k<=j;k++)
        lower[(size_t)(begin+j)*p+begin+k]=root[(size_t)k*s+j];
    return 1;
}
