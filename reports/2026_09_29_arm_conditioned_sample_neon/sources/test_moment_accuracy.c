static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t state=0x84c2179du;
static float next_value(void) { state=1664525u*state+1013904223u; return ((state>>8)*0x1p-23f-.5f)*.25f; }

static float check_sample_packing(const float *weighted,size_t n)
{
    float maximum=0;
    for(size_t begin=0;begin<n;begin+=CONDITIONED_MOMENT_BLOCK) {
        size_t end=begin+CONDITIONED_MOMENT_BLOCK<n?begin+CONDITIONED_MOMENT_BLOCK:n;
        float center=(float)begin+.5f*(float)(end-begin-1);
        float complex reference[5]={0},packed[5];float scale[5]={0};
        for(size_t k=begin;k<end;++k) {
            float delta=(float)k-center,power=1;
            float complex sample=weighted[2*k]+I*weighted[2*k+1];
            for(int order=0;order<5;++order) {
                reference[order]+=sample*power;scale[order]+=cabsf(sample)*fabsf(power);power*=delta;
            }
        }
        conditioned_accumulate_four_samples(weighted,begin,end,center,packed);
        for(int order=0;order<5;++order) {
            float error=cabsf(reference[order]-packed[order]);
            float normalized=error/fmaxf(1,scale[order]);
            if(normalized>maximum)maximum=normalized;
            assert(isfinite(crealf(packed[order]))&&isfinite(cimagf(packed[order])));
            assert(normalized<=2e-5f);
        }
    }
    return maximum;
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    float maximum_absolute=0,maximum_relative=0,maximum_screen_normalized=0,maximum_moment_normalized=0;
    for (size_t r=0;r<sizeof(rates)/sizeof(rates[0]);++r) {
        size_t n=(rates[r]+375)/750;
        float *weighted=calloc(2*n,sizeof(*weighted)); assert(weighted);
        for (int pattern=0;pattern<4;++pattern) {
            for (size_t k=0;k<2*n;++k) weighted[k]=pattern==0 ? next_value() :
                pattern==1 ? (float)((int)(k%19)-9)*.03125f :
                pattern==2 ? (k&1 ? -.125f : .125f) : (k%31==0 ? .25f : -.015625f);
            float moment_error=check_sample_packing(weighted,n);
            if(moment_error>maximum_moment_normalized)maximum_moment_normalized=moment_error;
            float reference[64],vectorized[64];
            assert(!conditioned_moment_magnitudes_reference(weighted,n,rates[r],41,reference));
            assert(!conditioned_moment_magnitudes_four_frequency(weighted,n,rates[r],41,vectorized));
            for (int f=0;f<41;++f) {
                assert(isfinite(reference[f])&&isfinite(vectorized[f]));
                float absolute=fabsf(reference[f]-vectorized[f]);
                float relative=absolute/fmaxf(fabsf(reference[f]),1e-6f);
                float screen_normalized=absolute/fmaxf(fabsf(reference[f]),.1f);
                if (absolute>maximum_absolute) maximum_absolute=absolute;
                if (relative>maximum_relative) maximum_relative=relative;
                if (screen_normalized>maximum_screen_normalized) maximum_screen_normalized=screen_normalized;
            }
        }
        memset(weighted,0,2*n*sizeof(*weighted));
        assert(check_sample_packing(weighted,n)==0);
        for(size_t k=0;k<2*n;++k)weighted[k]=(k&1)?-32768.0f:32767.0f;
        float extreme_error=check_sample_packing(weighted,n);
        if(extreme_error>maximum_moment_normalized)maximum_moment_normalized=extreme_error;
        free(weighted);
    }
    /* This records a real approximate-screen error bound, rather than relying
     * on bitwise equality with the FP64 accumulation path. */
    fprintf(stderr,"conditioned moments observed: max_abs=%.9g max_rel=%.9g max_screen_normalized=%.9g\n",maximum_absolute,maximum_relative,maximum_screen_normalized);
    assert(maximum_absolute<=.001f && maximum_screen_normalized<=.01f);
    printf("conditioned sample packing: max_moment_normalized=%.9g max_abs=%.9g max_rel=%.9g max_screen_normalized=%.9g all_rates=4 bins=41 zero=1 extreme=1\n",maximum_moment_normalized,maximum_absolute,maximum_relative,maximum_screen_normalized);
    return 0;
}
