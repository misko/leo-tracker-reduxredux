#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>

#define CFO_COUNT 24
#define WIDE_REGIONAL_BINS 21
#define LEO_PRESENCE_ANCHOR_STRIDE 1
#define LEO_PRESENCE_COARSE_FRAMES 2

typedef struct {
    int regional_count,regional_epochs[12],starts[12],stops[12],offsets[2],support[64];
    size_t n;
    float float_reference_real[12*45*CFO_COUNT],float_reference_imag[12*45*CFO_COUNT];
    float float_samples[256];
    double prefix[129],float_reference_energy[12],frequencies[24],grid[21*64];
} leo_presence_workspace;

static int coarse_frame_index(int slot) { return slot; }

#include "wide_regional_cfo.h"
#include "scout_stride_coarse.h"

static uint32_t state=392331;

static float random_value(void)
{
    state=1664525u*state+1013904223u;
    return (float)((int)(state>>16)-32768)*0x1p-15f;
}

static void check_even_cells(void)
{
    for (int taps=1;taps<=45;++taps) {
        float sample[90], r[45*24], i[45*24], re[45*12], im[45*12];
        float full[24]={0},stride[24]={0};
        for (int k=0;k<taps;++k) {
            sample[2*k]=random_value();sample[2*k+1]=random_value();
            for (int f=0;f<24;++f) {
                r[24*k+f]=random_value();i[24*k+f]=random_value();
                if (!(f&1)) { re[12*k+f/2]=r[24*k+f];im[12*k+f/2]=i[24*k+f]; }
            }
        }
        for (int rep=0;rep<5;++rep) {
            wide_regional_float_add(sample,r,i,taps,0.53125f,full);
            scout_stride_even_add(sample,re,im,taps,0.53125f,stride);
            for (int f=0;f<21;f+=2) assert(stride[f]==full[f]);
            for (int f=1;f<21;f+=2) assert(stride[f]==0);
        }
    }
}

static void check_odd_choices(void)
{
    leo_presence_workspace w={.n=12,.regional_count=6,.regional_epochs={0,1,5,6,10,11},
                             .offsets={0,20}};
    for (int k=0;k<12;++k) {
        w.stops[k]=2;
        w.float_reference_energy[k]=2;
        w.support[k]=24;
        for (int f=0;f<24;++f) {
            w.float_reference_real[k*45*24+f]=1;
            w.float_reference_real[k*45*24+24+f]=1;
        }
    }
    for (int k=0;k<128;++k) { w.float_samples[2*k]=1;w.prefix[k+1]=k+1; }
    for (int f=0;f<21;++f) {
        w.frequencies[f]=-800000+80000*f;
        for (int k=0;k<(int)w.n;++k) w.grid[f*w.n+k]=(f&1)?-INFINITY:0;
    }
    w.grid[0]=0.5;                 /* Lower endpoint can restore only bin 1. */
    w.grid[10*w.n+5]=0.75;         /* Best interior basin restores 9 and 11. */
    w.grid[8*w.n+6]=0.75;          /* Equal score, more distant frequency. */
    assert(scout_stride_neighbors(&w,128)==0);
    for (int f=1;f<21;f+=2) {
        for (int k=0;k<(int)w.n;++k) {
            int restored=(f==1&&k<2)||((f==9||f==11)&&(k==5||k==6));
            if (restored) assert(w.grid[f*w.n+k]==1);
            else assert(w.grid[f*w.n+k]==-INFINITY);
        }
    }
}

int main(void)
{
    check_even_cells();
    check_odd_choices();
    return 0;
}
