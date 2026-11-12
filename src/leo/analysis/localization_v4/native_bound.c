/* Isolated research kernel. LP64 LAPACKE C ABI; no Fortran character ABI. */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

typedef int32_t (*potrf_fn)(int32_t,char,int32_t,double*,int32_t);
typedef int32_t (*potrs_fn)(int32_t,char,int32_t,int32_t,const double*,int32_t,double*,int32_t);
typedef int32_t (*potri_fn)(int32_t,char,int32_t,double*,int32_t);
typedef int32_t (*pocon_fn)(int32_t,char,int32_t,const double*,int32_t,double,double*);
enum { NB_OK=0, NB_UNSUPPORTED=1, NB_NONFINITE=2, NB_SPD=3, NB_CONDITION=4, NB_MEMORY=5 };
typedef struct {
    int n,p,k,s,qmax,total,mats;
    int *offset,*columns,*matrix_offset,*shared,*private_index,*private_cols,*width;
} Layout;

void nb_free(void *pointer) {
    Layout *l=pointer;
    if (!l) return;
    free(l->offset);free(l->columns);free(l->matrix_offset);free(l->shared);
    free(l->private_index);free(l->private_cols);free(l->width);free(l);
}

void *nb_layout(int n,int p,int k,const int64_t *groups,const double *u,int *status) {
    *status=NB_UNSUPPORTED;
    if(n<1 || n>100000 || p<0 || p>512 || k<1 || k>2048) return NULL;
    Layout *l=calloc(1,sizeof(*l));
    unsigned char *active=calloc((size_t)k*(p?p:1),1);
    int *support=calloc(p?p:1,sizeof(int));
    if(!l || !active || !support) {free(l);free(active);free(support);*status=NB_MEMORY;return NULL;}
    l->n=n;l->p=p;l->k=k;
    l->offset=calloc(k+1,sizeof(int));l->matrix_offset=calloc(k+1,sizeof(int));
    l->shared=malloc((p?p:1)*sizeof(int));l->private_index=malloc((p?p:1)*sizeof(int));
    l->private_cols=malloc(2*k*sizeof(int));l->width=calloc(k,sizeof(int));
    if(!l->offset || !l->matrix_offset || !l->shared || !l->private_index ||
       !l->private_cols || !l->width) {*status=NB_MEMORY;goto fail;}
    for(int i=0;i<n;i++) for(int j=0;j<p;j++) if(u[(size_t)i*p+j]!=0.) active[groups[i]*p+j]=1;
    for(int j=0;j<p;j++) {
        for(int g=0;g<k;g++) support[j]+=active[g*p+j];
        l->shared[j]=support[j]>1?l->s++:-1;l->private_index[j]=-1;
    }
    for(int g=0;g<k;g++) {
        int q=0;
        for(int j=0;j<p;j++) if(active[g*p+j]) {
            q++;
            if(support[j]==1) {
                int d=l->width[g]++;
                if(d>=2) goto fail;
                l->private_index[j]=d;l->private_cols[2*g+d]=j;
            }
        }
        if(q>l->qmax)l->qmax=q;
        l->offset[g+1]=l->offset[g]+q;
        l->matrix_offset[g+1]=l->matrix_offset[g]+q*q;
        if(l->matrix_offset[g+1]>2000000)goto fail;
    }
    l->total=l->offset[k];l->mats=l->matrix_offset[k];
    l->columns=malloc((l->total?l->total:1)*sizeof(int));
    if(!l->columns) {*status=NB_MEMORY;goto fail;}
    for(int g=0;g<k;g++) {
        int z=l->offset[g];for(int j=0;j<p;j++)if(active[g*p+j])l->columns[z++]=j;
    }
    free(active);free(support);*status=NB_OK;return l;
fail:
    free(active);free(support);nb_free(l);return NULL;
}

/* All work belongs to one call; layout holds symbolic indices only. */
int nb_run(void *pointer,void *pf,void *ps,void *pi,void *pc,
 const double *y,const double *u,const double *sigma,const int64_t *groups,
 const double *power,const int64_t *prior,int t,const double *alpha,const double *pa,
 double beta0,double pb0,double v0,int budget,double min_rcond,
 double *mean,double *native,double *weight,double *precision,double *v,double *scalars,
 int *updates,double *returned_rates) {
    Layout *l=pointer;
    if(!l || !pf || !ps || !pi || !pc || budget<1 || t<0)return NB_UNSUPPORTED;
    int n=l->n,p=l->p,k=l->k,s=l->s,sz=s?s:1,code=NB_OK;
    potrf_fn potrf=(potrf_fn)pf;potrs_fn potrs=(potrs_fn)ps;
    potri_fn potri=(potri_fn)pi;pocon_fn pocon=(pocon_fn)pc;
    size_t count=(size_t)(l->mats?l->mats:1)+l->total+3*(size_t)sz*sz+
        6*(size_t)k*sz+13*(size_t)k+3*(t?t:1)+(p?p:1)+3*sz+(l->qmax?l->qmax:1);
    double *work=calloc(count,sizeof(double));
    if(!work)return NB_MEMORY;
    double *matrix=work,*rhs=matrix+(l->mats?l->mats:1),*a=rhs+l->total;
    double *root=a+(size_t)sz*sz,*cov=root+(size_t)sz*sz;
    double *e=cov+(size_t)sz*sz,*f=e+2*(size_t)k*sz;
    double *cross=f+2*(size_t)k*sz,*dinv=cross+2*(size_t)k*sz,*d=dinv+4*k,*b=d+4*k;
    double *rate=b+2*k,*next_rate=rate+k,*prate=next_rate+k,*next_prate=prate+(t?t:1);
    double *penergy=next_prate+(t?t:1),*diagonal=penergy+(t?t:1);
    double *energy=diagonal+(p?p:1),*bg=energy+k,*xg=bg+sz,*row=xg+sz;
    double *row_f=row+(l->qmax?l->qmax:1);
    /* Current group Gram/RHS, fused over actual active columns. */
    for(int i=0;i<n;i++) {
        int g=(int)groups[i],off=l->offset[g],q=l->offset[g+1]-off;
        double r=y[i]/sigma[i];
        for(int j=0;j<q;j++)row[j]=u[(size_t)i*p+l->columns[off+j]]/sigma[i];
        double *m=matrix+l->matrix_offset[g];
        for(int j=0;j<q;j++) {
            rhs[off+j]+=row[j]*r;
            for(int h=0;h<q;h++)m[j*q+h]+=row[j]*row[h];
        }
    }
    for(int g=0;g<k;g++)rate[g]=alpha[g];
    for(int j=0;j<t;j++)prate[j]=pa[j]/v0;
    double change=INFINITY,logdet=0.;int performed=0;
    for(int iteration=0;iteration<=budget;iteration++) {
        int final=(iteration==budget || (iteration>0 && change<1e-5));
        memset(a,0,(size_t)sz*sz*sizeof(double));memset(e,0,2*(size_t)k*sz*sizeof(double));
        memset(f,0,2*(size_t)k*sz*sizeof(double));memset(d,0,4*k*sizeof(double));
        memset(b,0,2*k*sizeof(double));memset(bg,0,sz*sizeof(double));
        for(int g=0;g<k;g++)weight[g]=alpha[g]/rate[g];
        for(int j=0;j<t;j++)v[j]=pa[j]/prate[j];
        for(int j=0;j<p;j++) {
            precision[j]=prior[j]<0?1.:v[prior[j]];
            if(!isfinite(precision[j]) || precision[j]<=0){code=NB_NONFINITE;goto done;}
            if(l->shared[j]>=0)a[l->shared[j]*(s+1)]=precision[j];
            else if(l->private_index[j]<0) {mean[j]=0.;diagonal[j]=1./precision[j];}
        }
        for(int g=0;g<k;g++) {
            int off=l->offset[g],q=l->offset[g+1]-off,nd=l->width[g];double w=power[g]*weight[g];
            for(int j=0;j<nd;j++)d[4*g+2*j+j]=precision[l->private_cols[2*g+j]];
            double *m=matrix+l->matrix_offset[g];
            for(int j=0;j<q;j++) {
                int col=l->columns[off+j],sj=l->shared[col],dj=l->private_index[col];
                if(sj>=0)bg[sj]+=w*rhs[off+j];else b[2*g+dj]+=w*rhs[off+j];
                for(int h=0;h<q;h++) {
                    int other=l->columns[off+h],sh=l->shared[other],dh=l->private_index[other];
                    double z=w*m[j*q+h];
                    if(sj>=0 && sh>=0)a[sh*s+sj]+=z;
                    else if(sj>=0)e[(2*g+dh)*sz+sj]+=z;
                    else if(sh<0)d[4*g+2*dj+dh]+=z;
                }
            }
        }
        /* Exact full-Gram 1-norm, before destructive Schur elimination. */
        double full_norm=0.;
        for(int j=0;j<s;j++) {
            double z=0.;for(int h=0;h<s;h++)z+=fabs(a[j*s+h]);
            for(int g=0;g<k;g++)for(int c=0;c<l->width[g];c++)z+=fabs(e[(2*g+c)*sz+j]);
            if(z>full_norm)full_norm=z;
        }
        for(int g=0;g<k;g++)for(int c=0;c<l->width[g];c++) {
            double z=0.;for(int j=0;j<s;j++)z+=fabs(e[(2*g+c)*sz+j]);
            for(int h=0;h<l->width[g];h++)z+=fabs(d[4*g+2*h+c]);
            if(z>full_norm)full_norm=z;
        }
        for(int j=0;j<p;j++)if(l->shared[j]<0 && l->private_index[j]<0 && precision[j]>full_norm)full_norm=precision[j];
        if(!isfinite(full_norm)){code=NB_NONFINITE;goto done;}
        logdet=0.;
        for(int j=0;j<p;j++)if(l->shared[j]<0 && l->private_index[j]<0)logdet+=log(precision[j]);
        for(int g=0;g<k;g++) {
            int nd=l->width[g];double *dd=d+4*g,*iv=dinv+4*g;
            memset(iv,0,4*sizeof(double));
            if(nd==1) {
                if(dd[0]<=0 || !isfinite(dd[0])){code=NB_SPD;goto done;}
                iv[0]=1./dd[0];logdet+=log(dd[0]);
            } else if(nd==2) {
                double det=dd[0]*dd[3]-dd[1]*dd[2],norm=fabs(dd[0])+fabs(dd[3]);
                if(dd[0]<=0 || dd[3]<=0 || det<=0 || !isfinite(det)){code=NB_SPD;goto done;}
                if(det<min_rcond*norm*norm){code=NB_CONDITION;goto done;}
                iv[0]=dd[3]/det;iv[1]=-dd[1]/det;iv[2]=-dd[2]/det;iv[3]=dd[0]/det;
                logdet+=log(det);
            }
            for(int z=l->offset[g];z<l->offset[g+1];z++) {
                int j=l->shared[l->columns[z]];if(j<0)continue;
                for(int c=0;c<nd;c++)for(int h=0;h<nd;h++)
                    f[(2*g+c)*sz+j]+=e[(2*g+h)*sz+j]*iv[2*h+c];
                for(int c=0;c<nd;c++)bg[j]-=f[(2*g+c)*sz+j]*b[2*g+c];
                for(int zz=l->offset[g];zz<l->offset[g+1];zz++) {
                    int h=l->shared[l->columns[zz]];if(h<0)continue;
                    for(int c=0;c<nd;c++)a[h*s+j]-=f[(2*g+c)*sz+j]*e[(2*g+c)*sz+h];
                }
            }
        }
        if(s) {
            double norm=0.;for(int h=0;h<s;h++){double z=0.;for(int j=0;j<s;j++)z+=fabs(a[h*s+j]);if(z>norm)norm=z;}
            memcpy(root,a,(size_t)s*s*sizeof(double));
            if(potrf(102,'L',s,root,s)){code=NB_SPD;goto done;}
            double rcond=0.;if(pocon(102,'L',s,root,s,norm,&rcond) || !isfinite(rcond) || rcond<min_rcond){code=NB_CONDITION;goto done;}
            for(int j=0;j<s;j++){xg[j]=bg[j];logdet+=2*log(root[j*(s+1)]);}
            if(potrs(102,'L',s,1,root,s,xg,s)){code=NB_SPD;goto done;}
            memcpy(cov,root,(size_t)s*s*sizeof(double));
            if(potri(102,'L',s,cov,s)){code=NB_SPD;goto done;}
            for(int j=0;j<s;j++)for(int h=0;h<j;h++)cov[j*s+h]=cov[h*s+j];
        }
        /* T=QF, with F supported only on each group's shared columns. */
        memset(row_f,0,sz*sizeof(double));memset(cross,0,2*(size_t)k*sz*sizeof(double));
        for(int g=0;g<k;g++)for(int c=0;c<l->width[g];c++) {
            for(int j=0;j<s;j++)row_f[j]+=fabs(f[(2*g+c)*sz+j]);
            for(int z=l->offset[g];z<l->offset[g+1];z++) {
                int h=l->shared[l->columns[z]];if(h<0)continue;
                double val=f[(2*g+c)*sz+h];
                for(int j=0;j<s;j++)cross[(2*g+c)*sz+j]+=cov[h*s+j]*val;
            }
        }
        /* Entrywise triangle bound on columns of [[Q,-T],[-T',Dinv+F'T]]. */
        double inverse_norm=0.;
        for(int j=0;j<s;j++) {
            double z=0.;for(int h=0;h<s;h++)z+=fabs(cov[j*s+h]);
            for(int g=0;g<k;g++)for(int c=0;c<l->width[g];c++)z+=fabs(cross[(2*g+c)*sz+j]);
            if(z>inverse_norm)inverse_norm=z;
        }
        for(int g=0;g<k;g++)for(int c=0;c<l->width[g];c++) {
            double z=0.;for(int j=0;j<s;j++)z+=(1.+row_f[j])*fabs(cross[(2*g+c)*sz+j]);
            for(int h=0;h<l->width[g];h++)z+=fabs(dinv[4*g+2*h+c]);
            if(z>inverse_norm)inverse_norm=z;
        }
        for(int j=0;j<p;j++)if(l->shared[j]<0 && l->private_index[j]<0 && 1./precision[j]>inverse_norm)inverse_norm=1./precision[j];
        if(p && (!isfinite(inverse_norm) || inverse_norm<=0 || 1./full_norm/inverse_norm<min_rcond)) {
            code=NB_CONDITION;goto done;
        }
        for(int j=0;j<p;j++)if(l->shared[j]>=0)mean[j]=xg[l->shared[j]];
        for(int g=0;g<k;g++) {
            int nd=l->width[g];double z[2]={b[2*g],b[2*g+1]};
            for(int pos=l->offset[g];pos<l->offset[g+1];pos++) {
                int j=l->shared[l->columns[pos]];if(j<0)continue;
                for(int c=0;c<nd;c++)z[c]-=e[(2*g+c)*sz+j]*xg[j];
            }
            for(int c=0;c<nd;c++){double val=0.;for(int h=0;h<nd;h++)val+=dinv[4*g+2*c+h]*z[h];mean[l->private_cols[2*g+c]]=val;}
        }
        memset(energy,0,k*sizeof(double));
        for(int i=0;i<n;i++) {
            int g=(int)groups[i];double val=0.;
            for(int z=l->offset[g];z<l->offset[g+1];z++){int j=l->columns[z];val+=u[(size_t)i*p+j]*mean[j];}
            native[i]=y[i]-val;double r=native[i]/sigma[i];energy[g]+=r*r;
            if(!isfinite(native[i])){code=NB_NONFINITE;goto done;}
        }
        if(final)break;
        for(int j=0;j<p;j++)if(l->shared[j]>=0)diagonal[j]=cov[l->shared[j]*(s+1)];
        for(int g=0;g<k;g++) {
            int off=l->offset[g],q=l->offset[g+1]-off,nd=l->width[g];double local[4]={0.,0.,0.,0.};
            for(int c=0;c<nd;c++)for(int h=0;h<nd;h++) {
                double val=dinv[4*g+2*c+h];
                for(int z=off;z<off+q;z++){int j=l->shared[l->columns[z]];if(j>=0)
                    val+=f[(2*g+c)*sz+j]*cross[(2*g+h)*sz+j];}
                local[2*c+h]=val;
            }
            for(int c=0;c<nd;c++)diagonal[l->private_cols[2*g+c]]=local[3*c];
            double variance=0.;double *m=matrix+l->matrix_offset[g];
            for(int j=0;j<q;j++)for(int h=0;h<q;h++) {
                int cj=l->columns[off+j],ch=l->columns[off+h],sj=l->shared[cj],sh=l->shared[ch];double val=0.;
                if(sj>=0 && sh>=0)val=cov[sh*s+sj];
                else if(sj<0 && sh<0)val=local[2*l->private_index[cj]+l->private_index[ch]];
                else {int sg=sj>=0?sj:sh,pr=l->private_index[sj<0?cj:ch];val=-cross[(2*g+pr)*sz+sg];}
                variance+=val*m[j*q+h];
            }
            next_rate[g]=beta0+power[g]*(energy[g]+fmax(0.,variance))/2.;
        }
        memset(penergy,0,(t?t:1)*sizeof(double));
        for(int j=0;j<p;j++) {
            if(!isfinite(diagonal[j]) || diagonal[j]<=0){code=NB_NONFINITE;goto done;}
            if(prior[j]>=0)penergy[prior[j]]+=mean[j]*mean[j]+diagonal[j];
        }
        change=0.;for(int g=0;g<k;g++){double z=fabs(log(next_rate[g]/rate[g]));if(!isfinite(z)){code=NB_NONFINITE;goto done;}if(z>change)change=z;rate[g]=next_rate[g];}
        for(int j=0;j<t;j++){next_prate[j]=pb0+penergy[j]/2.;double z=fabs(log(next_prate[j]/prate[j]));if(!isfinite(z)){code=NB_NONFINITE;goto done;}if(z>change)change=z;prate[j]=next_prate[j];}
        performed++;
    }
    for(int j=0;j<p;j++)logdet-=log(precision[j]);
    scalars[0]=fmax(0.,logdet);scalars[1]=change;*updates=performed;
    memcpy(returned_rates,rate,k*sizeof(double));
    if(!isfinite(scalars[0]) || !isfinite(change)){code=NB_NONFINITE;goto done;}
done:
    free(work);return code;
}
