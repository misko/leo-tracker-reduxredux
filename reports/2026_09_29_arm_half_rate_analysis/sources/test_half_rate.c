#define main half_rate_runner_main
#include "fused_probe.c"
#undef main
#include <assert.h>

int main(void){const unsigned long rates[]={2500000,5000000,7500000,10000000};for(int q=0;q<4;q++){size_t of=(rates[q]+375)/750,ef=(rates[q]/2+375)/750,od=rates[q]*120/1000,ed=(rates[q]/2)*120/1000,probe=(rates[q]/2)/50;assert(probe*50==rates[q]/2);leo_presence_complex *a=calloc(of,sizeof(*a)),*b=calloc(ef,sizeof(*b));short*x=calloc(od*4,sizeof(*x)),*y=calloc(ed*4,sizeof(*y));assert(a&&b&&x&&y);for(size_t k=0;k<of;k++)a[k]=(leo_presence_complex){k,-(double)k};for(size_t k=0;k<od*4;k++)x[k]=(short)(k*97u);assert(!half_rate_copy_templates(a,of,b,ef)&&!half_rate_copy_ci16(x,od,y,ed));for(size_t k=0;k<ef;k++){assert(b[k].re==a[2*k].re&&b[k].im==a[2*k].im);}for(size_t k=0;k<ed;k++)for(int c=0;c<4;c++)assert(y[4*k+c]==x[8*k+c]);assert(half_rate_copy_templates(a,ef*2-2,b,ef));assert(half_rate_copy_ci16(x,ed*2-2,y,ed));for(int epoch=0;epoch<(int)ef;epoch++)assert(2*epoch>=0&&2*epoch<(int)of);free(y);free(x);free(b);free(a);}puts("half-rate analysis passed: all rates lengths, 20ms windows, even selection, epoch x2, read bounds");return 0;}
