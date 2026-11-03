/* Research-only direct TLE -> compact ECEF ephemeris benchmark. */
#define _GNU_SOURCE
#include "SGP4.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <ctime>
#include <cstdint>
#include <sys/resource.h>
#ifdef ARM_TARGET
#include <sched.h>
#endif
static double now(clockid_t c){timespec t;clock_gettime(c,&t);return t.tv_sec+t.tv_nsec*1e-9;}
int main(int argc,char **argv){
 if(argc!=7)return 2;
#ifdef ARM_TARGET
 cpu_set_t cpus;CPU_ZERO(&cpus);CPU_SET(0,&cpus);if(sched_setaffinity(0,sizeof(cpus),&cpus))return 3;
#endif
 FILE *f=fopen(argv[1],"r");if(!f)return 2;
 unsigned ns;if(fscanf(f,"%u\n",&ns)!=1||ns>20000)return 2;
 int64_t start=strtoll(argv[2],nullptr,10);double base=atof(argv[3]),step=atof(argv[4]);unsigned nk=atoi(argv[5]);
 if(step<=0||nk<2||nk>2000)return 2;
 std::vector<elsetrec> sats(ns);double dummy=0;double setup=now(CLOCK_PROCESS_CPUTIME_ID);
 for(unsigned s=0;s<ns;s++){
  char l1[130],l2[130];if(!fgets(l1,130,f)||!fgets(l2,130,f)||strlen(l1)<69||strlen(l2)<69)return 2;
  l1[68]=l2[68]=0;for(int i=2;i<7;i++){if(l1[i]==' ')l1[i]='0';if(l2[i]==' ')l2[i]='0';}
  SGP4Funcs::twoline2rv(l1,l2,' ',' ','i',wgs72,dummy,dummy,dummy,sats[s]);
  sats[s].jdsatepochF=round(sats[s].jdsatepochF*1e8)/1e8;
 }fclose(f);setup=now(CLOCK_PROCESS_CPUTIME_ID)-setup;
 std::vector<double> output((size_t)ns*nk*6),jd(nk),fr(nk),co(nk),si(nk);
 double cpu=now(CLOCK_PROCESS_CPUTIME_ID),wall=now(CLOCK_MONOTONIC);
 for(unsigned k=0;k<nk;k++){
  int64_t epoch=start+llround((base+k*step)*1e9),day=epoch/86400000000000LL;
  jd[k]=2440587.5+(double)day;fr[k]=(double)(epoch-day*86400000000000LL)/86400000000000.0;
  double t=(jd[k]-2451545.0+fr[k])/36525.0;
  double sec=67310.54841+(876600.0*3600.0+8640184.812866)*t+.093104*t*t-6.2e-6*t*t*t;
  double deg=fmod(sec/240.,360.);if(deg<0)deg+=360.;double angle=deg*3.14159265358979323846/180.;co[k]=cos(angle);si[k]=sin(angle);
 }
 unsigned errors=0;
 for(unsigned s=0;s<ns;s++)for(unsigned k=0;k<nk;k++){
  double t=(jd[k]-sats[s].jdsatepoch)*1440.+(fr[k]-sats[s].jdsatepochF)*1440.;double p[3],v[3];
  SGP4Funcs::sgp4(sats[s],t,p,v);if(sats[s].error)errors++;
  double *o=output.data()+((size_t)s*nk+k)*6;
  o[0]=co[k]*p[0]+si[k]*p[1];o[1]=-si[k]*p[0]+co[k]*p[1];o[2]=p[2];
  o[3]=co[k]*v[0]+si[k]*v[1]+7.292115146706979e-5*o[1];
  o[4]=-si[k]*v[0]+co[k]*v[1]-7.292115146706979e-5*o[0];o[5]=v[2];
 }
 cpu=now(CLOCK_PROCESS_CPUTIME_ID)-cpu;wall=now(CLOCK_MONOTONIC)-wall;
 FILE *out=fopen(argv[6],"wb");if(!out||fwrite(output.data(),8,output.size(),out)!=output.size())return 3;fclose(out);
 rusage usage;getrusage(RUSAGE_SELF,&usage);
 printf("{\"satellites\":%u,\"knots\":%u,\"setup_cpu_seconds\":%.17g,\"propagation_cpu_seconds\":%.17g,\"propagation_wall_seconds\":%.17g,\"errors\":%u,\"peak_rss_kib\":%ld}\n",ns,nk,setup,cpu,wall,errors,usage.ru_maxrss);
 return errors?4:0;
}
