static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t state=0x84c2179du;
static float next_value(void) { state=1664525u*state+1013904223u; return ((state>>8)*0x1p-23f-.5f)*.25f; }

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    float maximum_absolute=0,maximum_relative=0,maximum_screen_normalized=0;
    double maximum_bound_fraction=0;
    for (size_t r=0;r<sizeof(rates)/sizeof(rates[0]);++r) {
        size_t n=(rates[r]+375)/750;
        float *weighted=calloc(2*n,sizeof(*weighted)); assert(weighted);
        for (int pattern=0;pattern<7;++pattern) {
            for (size_t k=0;k<n;++k) {
                if(pattern==0){weighted[2*k]=next_value();weighted[2*k+1]=next_value();}
                else if(pattern==1){weighted[2*k]=(float)((int)(k%19)-9)*.03125f;weighted[2*k+1]=(float)((int)(k%13)-6)*.025f;}
                else if(pattern==2){weighted[2*k]=(k&1)?-.125f:.125f;weighted[2*k+1]=(k&2)?.0625f:-.0625f;}
                else if(pattern==3){weighted[2*k]=k%31==0?.25f:-.015625f;weighted[2*k+1]=k%29==0?-.2f:.01f;}
                else if(pattern==4){double p=TAU*1300.0*k/rates[r];weighted[2*k]=(float)cos(p);weighted[2*k+1]=(float)sin(p);}
                else if(pattern==5){weighted[2*k]=weighted[2*k+1]=0;}
                else {weighted[2*k]=(k&1)?32767:-32768;weighted[2*k+1]=(k&2)?-32768:32767;}
            }
            float reference[64],vectorized[64];
            assert(!conditioned_moment_magnitudes_reference(weighted,n,rates[r],41,reference));
            assert(!conditioned_moment_magnitudes_four_frequency(weighted,n,rates[r],41,vectorized));
            for (int f=0;f<41;++f) {
                assert(isfinite(reference[f])&&isfinite(vectorized[f]));
                float absolute=fabsf(reference[f]-vectorized[f]);
                float relative=absolute/fmaxf(fabsf(reference[f]),1e-6f);
                float screen_normalized=absolute/fmaxf(fabsf(reference[f]),.1f);
                if(pattern<5) {
                    if (absolute>maximum_absolute) maximum_absolute=absolute;
                    if (relative>maximum_relative) maximum_relative=relative;
                    if (screen_normalized>maximum_screen_normalized) maximum_screen_normalized=screen_normalized;
                }

                double complex direct=0;double tail=0,polynomial_l1=0;
                double omega=TAU*100.0*f/rates[r];
                for(size_t begin=0;begin<n;begin+=CONDITIONED_MOMENT_BLOCK) {
                    size_t end=begin+CONDITIONED_MOMENT_BLOCK<n?begin+CONDITIONED_MOMENT_BLOCK:n;
                    double center=(double)begin+.5*(double)(end-begin-1);
                    for(size_t k=begin;k<end;++k) {
                        double complex sample=(double)weighted[2*k]+I*(double)weighted[2*k+1];
                        double x=fabs(omega*((double)k-center)),a=cabs(sample);
                        direct+=sample*rotate(-omega*(double)k);
                        double power=1,factorial=1,polynomial=1;
                        for(int order=1;order<=CONDITIONED_MOMENT_DEGREE;++order) {
                            power*=x;factorial*=order;polynomial+=power/factorial;
                        }
                        power*=x;factorial*=CONDITIONED_MOMENT_DEGREE+1;
                        tail+=a*exp(x)*power/factorial;
                        polynomial_l1+=a*polynomial;
                    }
                }
                double bound=tail+2048.0*FLT_EPSILON*polynomial_l1;
                double direct_error=fabs((double)vectorized[f]-cabs(direct));
                assert(direct_error<=bound+1e-9);
                if(bound>0 && direct_error/bound>maximum_bound_fraction)
                    maximum_bound_fraction=direct_error/bound;
            }
        }
        free(weighted);
    }
    /* This records a real approximate-screen error bound, rather than relying
     * on bitwise equality with the FP64 accumulation path. */
    fprintf(stderr,"conditioned moments observed: max_abs=%.9g max_rel=%.9g max_screen_normalized=%.9g\n",maximum_absolute,maximum_relative,maximum_screen_normalized);
    assert(maximum_screen_normalized<=.01f);
    printf("low-order conditioned direct-DFT bound: degree=%d block=%d max_bound_fraction=%.9g scalar_vector_max_abs=%.9g max_rel=%.9g max_screen_normalized=%.9g all_rates=4 bins=41 zero=1 extreme=1 tone=1 partial_tail=1\n",CONDITIONED_MOMENT_DEGREE,CONDITIONED_MOMENT_BLOCK,maximum_bound_fraction,maximum_absolute,maximum_relative,maximum_screen_normalized);
    return 0;
}
