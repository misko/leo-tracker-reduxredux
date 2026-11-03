static int regional_count;static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
static void run_rate(uint32_t rate,double *max_error){
 size_t n=(rate+375)/750,count=rate/50;leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));assert(exact&&control);
 for(size_t k=0;k<n;k++){exact[k]=(leo_presence_complex){cos(.013*k),sin(.013*k)};control[k]=(leo_presence_complex){cos(.019*k),-sin(.019*k)};}
 leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);assert(w);
 for(size_t k=0;k<count;k++){int16_t re=(int16_t)((k*7919u+17u)&65535u),im=(int16_t)((k*3571u+32768u)&65535u);if(k==0)re=INT16_MIN;if(k+1==count)im=INT16_MAX;w->samples[k]=(double)re+I*(double)im;w->float_samples[2*k]=(float)re/32768.0f;w->float_samples[2*k+1]=(float)im/32768.0f;}
 const double cfos[]={-317500,0,248750};for(int q=0;q<3;q++){double reference[3],approx[3];assert(!glrt(w,count,(int)n/4,cfos[q],0,16,1,reference));assert(!glrt_float_final(w,count,(int)n/4,cfos[q],approx));for(int j=0;j<2;j++){double e=fabs(reference[j]-approx[j]);if(e>*max_error)*max_error=e;assert(e<.015);}assert(fabs(reference[2]-approx[2])<=2.0/(512*SYMBOL_S));}
 memset(w->samples,0,count*sizeof(*w->samples));memset(w->float_samples,0,2*count*sizeof(*w->float_samples));double reference[3],approx[3];assert(!glrt(w,count-1,(int)n/3,12345,0,16,1,reference));assert(!glrt_float_final(w,count-1,(int)n/3,12345,approx));assert(reference[0]==0&&reference[1]==0&&reference[2]==0);assert(approx[0]==0&&approx[1]==0&&approx[2]==0);
 leo_presence_destroy(w);free(control);free(exact);
}
int main(void){double max_error=0;uint32_t rates[]={2500000,5000000,7500000,10000000};for(int k=0;k<4;k++)run_rate(rates[k],&max_error);float_final_free();printf("full FP32 final GLRT passed FP64 reference, flat, tails, extrema, and all rates; max_score_error=%.17g\n",max_error);}
