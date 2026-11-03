#define _POSIX_C_SOURCE 200809L
#include "coarse_winograd.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>

static uint32_t state=1;
static float random_value(void){state=1664525*state+1013904223;return (float)(int32_t)state/2147483648.0f;}
static double now(void){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return t.tv_sec+1e-9*t.tv_nsec;}

static float one_case(float scale,int coherent)
{
    float xr[6],xi[6],hr[3][CW_CFO],hi[3][CW_CFO],ar[4][CW_CFO],ai[4][CW_CFO],br[4][CW_CFO],bi[4][CW_CFO];
    for(int k=0;k<6;++k){xr[k]=scale*(coherent?1.0f:random_value());xi[k]=scale*(coherent?-0.75f:random_value());}
    for(int k=0;k<3;++k)for(int f=0;f<CW_CFO;++f){hr[k][f]=coherent?.5f:random_value();hi[k][f]=coherent?-.25f:random_value();}
    cw_filters p;cw_prepare(hr,hi,&p);cw_direct(xr,xi,hr,hi,ar,ai);cw_four(xr,xi,&p,br,bi);
    float worst=0;for(int j=0;j<4;++j)for(int f=0;f<CW_CFO;++f){worst=fmaxf(worst,fabsf(ar[j][f]-br[j][f]));worst=fmaxf(worst,fabsf(ai[j][f]-bi[j][f]));}return worst;
}

int main(void)
{
    float worst=0;for(int rate=0;rate<4;++rate)for(int n=0;n<2000;++n)worst=fmaxf(worst,one_case(1.0f,0));
    worst=fmaxf(worst,one_case(1.0f,1));worst=fmaxf(worst,one_case(1.0f/32768,0));
    assert(worst<2e-5f);
    float xr[6]={0},xi[6]={0},hr[3][CW_CFO]={{0}},hi[3][CW_CFO]={{0}},y[4][CW_CFO],z[4][CW_CFO];
    cw_filters p;cw_prepare(hr,hi,&p);cw_four(xr,xi,&p,y,z);for(int j=0;j<4;++j)for(int f=0;f<CW_CFO;++f)assert(y[j][f]==0&&z[j][f]==0);
    for(int k=0;k<6;++k){xr[k]=random_value();xi[k]=random_value();}for(int k=0;k<3;++k)for(int f=0;f<CW_CFO;++f){hr[k][f]=random_value();hi[k][f]=random_value();}cw_prepare(hr,hi,&p);
    volatile float sink=0;const int loops=400000;double t=now();for(int n=0;n<loops;++n){cw_direct(xr,xi,hr,hi,y,z);sink+=y[n&3][n%CW_CFO];}double direct=now()-t;
    t=now();for(int n=0;n<loops;++n){cw_four(xr,xi,&p,y,z);sink+=y[n&3][n%CW_CFO];}double winograd=now()-t;
    printf("worst_abs_error=%.9g direct_ms=%.3f winograd_ms=%.3f ratio=%.4f sink=%g\n",worst,1000*direct,1000*winograd,winograd/direct,(double)sink);
}
