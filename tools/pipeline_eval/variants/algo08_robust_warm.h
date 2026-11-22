/* Experimental fixed-model initialization for the unchanged native Gamma updates. */
typedef struct {
    int valid,n,p,k,t;
    double beta0,pb0,v0;
    double alpha[2048],pa[512];
    double noise_rate[2048],prior_rate[512];
} WarmRates;

size_t nb_warm_size(void) { return sizeof(WarmRates); }

static int matching_rates(const WarmRates *warm,const Layout *l,int t,const double *alpha,
                          const double *pa,double beta0,double pb0,double v0) {
    return warm && warm->valid && t<=512 && warm->n==l->n && warm->p==l->p &&
        warm->k==l->k && warm->t==t && beta0==warm->beta0 && pb0==warm->pb0 && v0==warm->v0 &&
        !memcmp(alpha,warm->alpha,l->k*sizeof(double)) && !memcmp(pa,warm->pa,t*sizeof(double));
}

static void cache_rates(WarmRates *warm,const Layout *l,int t,const double *alpha,
                        const double *pa,double beta0,double pb0,double v0,
                        const double *rate,const double *prate) {
    if (!warm || t>512) return;
    warm->valid=1;warm->n=l->n;warm->p=l->p;warm->k=l->k;warm->t=t;
    warm->beta0=beta0;warm->pb0=pb0;warm->v0=v0;
    memcpy(warm->alpha,alpha,l->k*sizeof(double));
    memcpy(warm->pa,pa,t*sizeof(double));
    memcpy(warm->noise_rate,rate,l->k*sizeof(double));
    memcpy(warm->prior_rate,prate,t*sizeof(double));
}
