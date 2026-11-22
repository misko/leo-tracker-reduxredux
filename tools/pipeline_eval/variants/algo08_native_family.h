/* Second Schur complement after the qualified track-private elimination. */
#define FAMILY_LIMIT 4
#define SHARED_LIMIT 512

struct FamilyLayout {
    int radio, count;
    int size[SHARED_LIMIT], columns[SHARED_LIMIT][FAMILY_LIMIT];
};

typedef void (*gemm_fn)(int, int, int, int, int, int, double, const double *, int,
                        const double *, int, double, double *, int);
static _Thread_local gemm_fn family_gemm;
static _Thread_local uint64_t family_counts[6];

void nb_family_gemm(void *operation) { family_gemm = (gemm_fn)operation; }
void nb_family_counts(uint64_t *out) { memcpy(out, family_counts, sizeof family_counts); }

static int component(int *parent, int index) {
    while (index != parent[index]) {
        parent[index] = parent[parent[index]];
        index = parent[index];
    }
    return index;
}

static struct FamilyLayout *family_layout(const Layout *l) {
    int s = l->s;
    if (s < FAMILY_LIMIT + 3) return NULL;
    unsigned char *adjacent = calloc((size_t)s*s, 1);
    if (!adjacent) return NULL;
    for (int g=0;g<l->k;g++) {
        for (int j=l->offset[g];j<l->offset[g+1];j++) {
            int x=l->shared[l->columns[j]];
            if (x<0) continue;
            for (int h=j+1;h<l->offset[g+1];h++) {
                int y=l->shared[l->columns[h]];
                if (y>=0) adjacent[y*s+x]=1;
            }
        }
    }
    int parent[SHARED_LIMIT], size[SHARED_LIMIT] = {0}, radio=s;
    for (int j=0;j<s;j++) parent[j]=j;
    /* The layout preserves design-column order. Find separated components in
       its trailing shared columns, with no satellite identifiers or thresholds. */
    for (int j=s-1;j>0;j--) {
        int joins[SHARED_LIMIT], count=0, total=1;
        for (int h=j+1;h<s;h++) if (adjacent[h*s+j]) {
            int root=component(parent,h), used=0;
            for (int q=0;q<count;q++) used|=joins[q]==root;
            if (!used) { joins[count++]=root; total+=size[root]; }
        }
        if (total>FAMILY_LIMIT) break;
        for (int q=0;q<count;q++) parent[joins[q]]=j;
        size[j]=total;
        radio=j;
    }
    free(adjacent);
    if (s-radio<FAMILY_LIMIT+1) return NULL;
    struct FamilyLayout *out=calloc(1,sizeof(*out));
    if (!out) return NULL;
    out->radio=radio;
    int index[SHARED_LIMIT];
    for (int j=0;j<s;j++) index[j]=-1;
    for (int j=radio;j<s;j++) {
        int root=component(parent,j);
        if (index[root]<0) index[root]=out->count++;
        int family=index[root];
        out->columns[family][out->size[family]++]=j;
    }
    return out;
}

static double matrix_norm1(int n, const double *matrix) {
    double norm=0.;
    for (int j=0;j<n;j++) {
        double sum=0.;
        for (int i=0;i<n;i++) sum+=fabs(matrix[j*n+i]);
        if (!isfinite(sum)) return INFINITY;
        if (sum>norm) norm=sum;
    }
    return norm;
}

static int small_inverse(int m, const double *a, double *inverse, double *logdet) {
    double lower[FAMILY_LIMIT*FAMILY_LIMIT]={0};
    for (int i=0;i<m;i++) for (int j=0;j<=i;j++) {
        double v=a[j*m+i];
        for (int k=0;k<j;k++) v-=lower[i*m+k]*lower[j*m+k];
        if (i==j) {
            if (v<=0. || !isfinite(v)) return 0;
            lower[i*m+i]=sqrt(v);
            *logdet+=log(v);
        } else lower[i*m+j]=v/lower[j*m+j];
    }
    for (int j=0;j<m;j++) {
        double *column=inverse+j*m;
        for (int i=0;i<m;i++) {
            double v=(i==j);
            for (int k=0;k<i;k++) v-=lower[i*m+k]*column[k];
            column[i]=v/lower[i*m+i];
        }
        for (int i=m-1;i>=0;i--) {
            double v=column[i];
            for (int k=i+1;k<m;k++) v-=lower[k*m+i]*column[k];
            column[i]=v/lower[i*m+i];
        }
    }
    return 1;
}

static int family_factor(const struct FamilyLayout *layout, int s, const double *a,
                          const double *rhs, double norm, double min_rcond,
                          potrf_fn potrf, potrs_fn potrs, potri_fn potri, pocon_fn pocon,
                          double *root, double *cov, double *mean, double *work,
                          double *logdet) {
    if (!layout || !family_gemm) return 0;
    enum { COLUMN_MAJOR=102, NO_TRANSPOSE=111, TRANSPOSE=112 };
    int r=layout->radio, n=s-r;
    double *transfer=work, *conditional=transfer+(size_t)r*n;
    double local[FAMILY_LIMIT*FAMILY_LIMIT], local_inverse[SHARED_LIMIT][FAMILY_LIMIT];
    double volume=0.;
    family_counts[0]++;
    for (int f=0;f<layout->count;f++) {
        int q=layout->size[f];
        const int *columns=layout->columns[f];
        double inverse[FAMILY_LIMIT*FAMILY_LIMIT];
        for (int j=0;j<q;j++) for (int i=0;i<q;i++) local[j*q+i]=a[columns[j]*s+columns[i]];
        if (!small_inverse(q,local,inverse,&volume)) return 0;
        for (int i=0;i<q;i++) {
            int ix=columns[i]-r;
            for (int j=0;j<q;j++) local_inverse[ix][j]=inverse[j*q+i];
            double v=0.;
            for (int j=0;j<q;j++) v+=inverse[j*q+i]*rhs[columns[j]];
            conditional[ix]=v;
            for (int k=0;k<r;k++) {
                double x=0.;
                for (int j=0;j<q;j++) x+=inverse[j*q+i]*a[columns[j]*s+k];
                transfer[k*n+ix]=x;
            }
        }
    }
    for (int i=0;i<r;i++) memcpy(root+i*r,a+i*s,r*sizeof(double));
    const double *connection=a+r*s;
    family_gemm(COLUMN_MAJOR,NO_TRANSPOSE,NO_TRANSPOSE,r,r,n,-1.,connection,s,
                transfer,n,1.,root,r);
    double radio_norm=matrix_norm1(r,root), rcond;
    if (potrf(COLUMN_MAJOR,'L',r,root,r) ||
        pocon(COLUMN_MAJOR,'L',r,root,r,radio_norm,&rcond) ||
        !isfinite(rcond) || rcond<min_rcond) return 0;
    for (int j=0;j<r;j++) {
        mean[j]=rhs[j];
        volume+=2*log(root[j*(r+1)]);
    }
    for (int j=0;j<n;j++) for (int i=0;i<r;i++) mean[i]-=connection[j*s+i]*conditional[j];
    if (potrs(COLUMN_MAJOR,'L',r,1,root,r,mean,r) || potri(COLUMN_MAJOR,'L',r,root,r)) return 0;
    for (int j=0;j<r;j++) for (int i=0;i<j;i++) root[j*r+i]=root[i*r+j];
    for (int j=0;j<r;j++) memcpy(cov+j*s,root+j*r,r*sizeof(double));
    family_gemm(COLUMN_MAJOR,NO_TRANSPOSE,TRANSPOSE,r,n,r,-1.,root,r,transfer,n,
                0.,cov+r*s,s);
    family_gemm(COLUMN_MAJOR,NO_TRANSPOSE,NO_TRANSPOSE,n,n,r,-1.,transfer,n,cov+r*s,s,
                0.,cov+r*s+r,s);
    for (int j=r;j<s;j++) for (int i=0;i<r;i++) cov[i*s+j]=cov[j*s+i];
    for (int f=0;f<layout->count;f++) {
        const int *columns=layout->columns[f];
        for (int j=0;j<layout->size[f];j++) for (int i=0;i<layout->size[f];i++)
            cov[columns[j]*s+columns[i]]+=local_inverse[columns[i]-r][j];
    }
    for (int j=0;j<n;j++) {
        double x=conditional[j];
        for (int i=0;i<r;i++) x-=transfer[i*n+j]*mean[i];
        mean[r+j]=x;
    }
    /* The reconstructed covariance still undergoes the original full native
       condition check including the earlier track-private eliminations. */
    if (!isfinite(volume) || 1./norm/matrix_norm1(s,cov)<min_rcond) return 0;
    *logdet+=volume;
    family_counts[1]++;
    family_counts[2]+=s;
    family_counts[3]+=r;
    family_counts[4]+=(uint64_t)s*s*s;
    family_counts[5]+=(uint64_t)r*r*r;
    return 1;
}
