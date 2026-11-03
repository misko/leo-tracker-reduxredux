/* Research prototype: bounded-memory all-track scoring from a shared ephemeris.
 * No radio, database, Python or report machinery in the numerical loop.
 * Input is a local test fixture, not a public persisted contract. */
#define _POSIX_C_SOURCE 200809L
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <sys/resource.h>
#ifdef ARM_TARGET
#include <sched.h>
#endif

typedef struct { uint32_t n,weight; double *t,*y; unsigned char *train; } Track;
typedef struct { int id,tau; double held,fit,offset; } Winner;
static void readn(FILE *f,void *p,size_t n,size_t size) {if(fread(p,size,n,f)!=n){fprintf(stderr,"short input\n");exit(2);}}
static double now(clockid_t c){struct timespec t;clock_gettime(c,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static double dot(const double *a,const double *b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
static void state(const double *s,unsigned knots,double base,double step,double t,double *p,double *v){
 double q=(t-base)/step;unsigned i=(unsigned)floor(q);if(i>=knots-1)i=knots-2;
 double u=q-i,u2=u*u,u3=u2*u;const double *a=s+6*i,*b=a+6;
 for(int j=0;j<3;j++){
  p[j]=(2*u3-3*u2+1)*a[j]+(u3-2*u2+u)*step*a[j+3]+(-2*u3+3*u2)*b[j]+(u3-u2)*step*b[j+3];
  v[j]=((6*u2-6*u)*a[j]+(-6*u2+6*u)*b[j])/step+(3*u2-4*u+1)*a[j+3]+(3*u2-2*u)*b[j+3];
 }
}
/* Cubic Bezier convex hull encloses each entire Hermite segment. Reject only
 * when its four control points are below the local horizon. Conservative for
 * this interpolant, not a bound on interpolation error relative to SGP4. */
static int possible(const double *s,unsigned knots,double base,double step,const Track *t,const double *site){
 int lo=(int)floor((t->t[0]-5-base)/step),hi=(int)floor((t->t[t->n-1]+5-base)/step);
 if(lo<0)lo=0;if(hi>(int)knots-2)hi=(int)knots-2;
 double plane=dot(site,site+3);
 for(int i=lo;i<=hi;i++){
  const double *a=s+6*i,*b=a+6;
  double x=dot(a,site+3)-plane,y=dot(b,site+3)-plane;
  if(x>=0||y>=0||x+step*dot(a+3,site+3)/3>=0||y-step*dot(b+3,site+3)/3>=0)return 1;
 }return 0;
}

int main(int argc,char **argv){
 if(argc!=2)return 2;
#ifdef ARM_TARGET
 cpu_set_t cpus;CPU_ZERO(&cpus);CPU_SET(0,&cpus);if(sched_setaffinity(0,sizeof(cpus),&cpus))return 3;
#endif
 FILE *f=fopen(argv[1],"rb");if(!f)return 2;uint32_t h[5];readn(f,h,5,4);
 unsigned ns=h[1],nk=h[2],nt=h[3],np=h[4];
 if(h[0]!=0x31434f4c||ns>20000||nk<2||nk>2000||nt>128||np>16||!ns||!nt||!np)return 2;
 double grid[2];readn(f,grid,2,8);double base=grid[0],step=grid[1];if(!(step>0))return 2;
 double *sites=calloc(np*6,8);Track *tracks=calloc(nt,sizeof(Track));int32_t *ids=calloc(ns,4);
 double *states=calloc((size_t)ns*nk*6,8);Winner *wins=calloc(np*nt,sizeof(Winner));
 if(!sites||!tracks||!ids||!states||!wins)return 3;readn(f,sites,np*6,8);
 unsigned maxn=0;
 for(unsigned t=0;t<nt;t++){
  uint32_t dims[2];readn(f,dims,2,4);Track *a=tracks+t;a->n=dims[0];a->weight=dims[1];
  if(a->n<6||a->n>40000||!a->weight)return 2;if(a->n>maxn)maxn=a->n;
  a->t=calloc(a->n,8);a->y=calloc(a->n,8);a->train=calloc(a->n,1);if(!a->t||!a->y||!a->train)return 3;
  readn(f,a->t,a->n,8);readn(f,a->y,a->n,8);readn(f,a->train,a->n,1);
  unsigned train=0;for(unsigned j=0;j<a->n;j++){
   if(!isfinite(a->t[j])||!isfinite(a->y[j])||a->train[j]>1||a->t[j]-5<base||a->t[j]+5>base+(nk-1)*step||(j&&a->t[j]<a->t[j-1]))return 2;
   train+=a->train[j];
  }if(!train||train==a->n)return 2;
 }
 readn(f,ids,ns,4);readn(f,states,(size_t)ns*nk*6,8);if(fgetc(f)!=EOF)return 2;fclose(f);
 double *res=calloc((size_t)11*maxn,8);if(!res)return 3;
 for(unsigned i=0;i<np*nt;i++){wins[i].id=-1;wins[i].held=INFINITY;wins[i].fit=INFINITY;}
 size_t rejected=0,evaluated=0;double cpu=now(CLOCK_PROCESS_CPUTIME_ID),wall=now(CLOCK_MONOTONIC);
 for(unsigned pi=0;pi<np;pi++)for(unsigned ti=0;ti<nt;ti++){
  Track *tr=tracks+ti;const double *site=sites+pi*6;Winner *w=wins+pi*nt+ti;
  unsigned ntrain=0;for(unsigned j=0;j<tr->n;j++)ntrain+=tr->train[j];
  for(unsigned si=0;si<ns;si++){
   const double *s=states+(size_t)si*nk*6;
   if(!possible(s,nk,base,step,tr,site)){rejected++;continue;}evaluated++;
   int visible=0,besttau=0;double bestfit=INFINITY,bestheld=INFINITY,bestoffset=0;
   for(int tau=-5;tau<=5;tau++){
    double *r=res+(tau+5)*maxn,offset=0;
    for(unsigned j=0;j<tr->n;j++){
     double p[3],v[3],delta[3];state(s,nk,base,step,tr->t[j]+tau,p,v);
     for(int k=0;k<3;k++)delta[k]=p[k]-site[k];
     if(dot(delta,site+3)>=0)visible=1;
     double pred=-11200000000.0/299792.458*dot(delta,v)/sqrt(dot(delta,delta));
     r[j]=tr->y[j]-pred;if(tr->train[j])offset+=r[j];
    }offset/=ntrain;double a=0,b=0;
    for(unsigned j=0;j<tr->n;j++){double e=r[j]-offset;if(tr->train[j])a+=e*e;else b+=e*e;}
    double fit=sqrt(a/ntrain),held=sqrt(b/(tr->n-ntrain));
    if(fit<bestfit){bestfit=fit;bestheld=held;bestoffset=offset;besttau=tau;}
   }
   if(visible&&(bestheld<w->held||(bestheld==w->held&&(bestfit<w->fit||(bestfit==w->fit&&ids[si]<w->id))))){
    w->id=ids[si];w->tau=besttau;w->fit=bestfit;w->held=bestheld;w->offset=bestoffset;
   }
  }
 }
 cpu=now(CLOCK_PROCESS_CPUTIME_ID)-cpu;wall=now(CLOCK_MONOTONIC)-wall;struct rusage usage;getrusage(RUSAGE_SELF,&usage);
 printf("{\"cpu_seconds\":%.17g,\"wall_seconds\":%.17g,\"peak_rss_kib\":%ld,\"rejected_blocks\":%zu,\"evaluated_blocks\":%zu,\"points\":[",cpu,wall,usage.ru_maxrss,rejected,evaluated);
 for(unsigned pi=0;pi<np;pi++){
  double loss=0,weight=0;for(unsigned ti=0;ti<nt;ti++){Winner *w=wins+pi*nt+ti;double capped=fmin(800,w->held);loss+=tracks[ti].weight*capped*capped;weight+=tracks[ti].weight;}
  printf("%s{\"score_hz\":%.17g,\"tracks\":[",pi?",":"",sqrt(loss/weight));
  for(unsigned ti=0;ti<nt;ti++){Winner *w=wins+pi*nt+ti;
   printf("%s{\"candidate_id\":%d,\"tau_s\":%d,\"held_hz\":",ti?",":"",w->id,w->tau);
   if(w->id<0)printf("null,\"fit_hz\":null,\"offset_hz\":null}");else printf("%.17g,\"fit_hz\":%.17g,\"offset_hz\":%.17g}",w->held,w->fit,w->offset);
  }printf("]}");
 }printf("]}\n");
 for(unsigned t=0;t<nt;t++){free(tracks[t].t);free(tracks[t].y);free(tracks[t].train);}free(tracks);free(sites);free(ids);free(states);free(wins);free(res);return 0;
}
