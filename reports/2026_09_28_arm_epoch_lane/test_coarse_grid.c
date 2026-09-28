#include "presence.h"
#include "fft.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

void leo_fft_forward_range(leo_fft *fft,const double complex *input,size_t used,
    size_t first,size_t count)
{
    (void)used;(void)first;(void)count;leo_fft_forward(fft,input);
}

static uint32_t random_state=UINT32_C(0x7f4a7c15);
static double random_value(void)
{
    random_state=random_state*UINT32_C(1664525)+UINT32_C(1013904223);
    return ((int32_t)(random_state>>8))*0x1p-25;
}

int main(int argc,char **argv)
{
    assert(argc==2);
    FILE *output=fopen(argv[1],"wb");assert(output);
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for (size_t r=0;r<4;++r) {
        uint32_t rate=rates[r];size_t n=(rate+375)/750,full=rate/50;
        leo_presence_complex *exact=calloc(n,sizeof(*exact));
        leo_presence_complex *control=calloc(n,sizeof(*control));
        leo_presence_complex *samples=calloc(full,sizeof(*samples));
        double *grid=calloc(11*n,sizeof(*grid));
        assert(exact&&control&&samples&&grid);
        for (size_t k=0;k<n;++k) {
            exact[k]=(leo_presence_complex){random_value(),random_value()};
            control[k]=(leo_presence_complex){random_value(),random_value()};
        }
        for (size_t k=0;k<full;++k)
            samples[k]=(leo_presence_complex){random_value()*1000,random_value()*1000};
        leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);assert(w);
        const size_t counts[]={full,2*n+17};
        for (size_t c=0;c<2;++c) {
            assert(!leo_presence_coarse(w,samples,counts[c],grid));
            assert(fwrite(grid,sizeof(*grid),11*n,output)==11*n);
        }
        for (size_t k=0;k<full;++k) samples[k]=(leo_presence_complex){0};
        assert(!leo_presence_coarse(w,samples,full,grid));
        for (size_t k=0;k<11*n;++k) assert(grid[k]==0);
        assert(fwrite(grid,sizeof(*grid),11*n,output)==11*n);
        leo_presence_destroy(w);free(grid);free(samples);free(control);free(exact);
    }
    assert(!fclose(output));puts("coarse grid cases written");return 0;
}
