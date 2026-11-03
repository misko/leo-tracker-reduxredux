#define main proposal_probe_main
#include "proposal_core.c"
#undef main
#include <assert.h>

static void test_rate(size_t rate)
{
    size_t n=(rate+375)/750,z=next_power2(n);
    fftwf_complex *src=fftwf_alloc_complex(n),*shifted=fftwf_alloc_complex(n);
    fftwf_complex *out=fftwf_alloc_complex(z),*shift_out=fftwf_alloc_complex(z);
    assert(src&&shifted&&out&&shift_out&&z>=n&&(z&(z-1))==0);
    memset(src,0,n*sizeof(*src));bank b;assert(!bank_init(&b,src,n,(double)rate));resample_periodic(&b,src,out);
    for(size_t k=0;k<z;k++)assert(out[k][0]==0&&out[k][1]==0);

    for(size_t k=0;k<n;k++){src[k][0]=(float)(3*k+1);src[k][1]=(float)(7*k-2);}
    resample_periodic(&b,src,out);
    size_t k=z-1,scaled=k*n,q=scaled/z,r=scaled%z;
    float f=(float)r/(float)z;
    assert(out[k][0]==src[q][0]+f*(src[0][0]-src[q][0]));
    assert(out[k][1]==src[q][1]+f*(src[0][1]-src[q][1]));

    size_t shift=17%n;
    for(size_t j=0;j<n;j++){shifted[j][0]=src[(j+n-shift)%n][0];shifted[j][1]=src[(j+n-shift)%n][1];}
    resample_periodic(&b,shifted,shift_out);
    for(size_t j=0;j<z;j++){
        size_t x=j*n,base=x/z,frac=x%z;
        size_t a=(base+n-shift)%n,b=(a+1)%n;float g=(float)frac/(float)z;
        assert(shift_out[j][0]==src[a][0]+g*(src[b][0]-src[a][0]));
        assert(shift_out[j][1]==src[a][1]+g*(src[b][1]-src[a][1]));
        size_t mapped=map_fft_index(j,n,z);assert(mapped<n);
        double exact=(double)j*n/z,err=fabs((double)mapped-exact);
        if(err>n/2)err=n-err;
        assert(err<=0.5000001);
    }
    bank_free(&b);fftwf_free(shift_out);fftwf_free(out);fftwf_free(shifted);fftwf_free(src);
}

static void test_original_grid_peak_distance(void)
{
    enum {N=3333,Z=4096};float *score=calloc(Z,sizeof(*score));ranked *work=malloc(Z*sizeof(*work));int out[TOP];assert(score&&work);
    score[0]=10;score[1]=1;score[Z-1]=1;
    size_t near=(3*Z+N/2)/N,far=(9*Z+N/2)/N;
    score[near]=9;score[near-1]=1;score[near+1]=1;
    score[far]=8;score[far-1]=1;score[far+1]=1;
    int used=peaks(score,Z,N,out,work);assert(used==2);assert(out[0]==0&&out[1]==9);
    free(work);free(score);
}

int main(void)
{
    const size_t rates[]={2500000,5000000,7500000,10000000};
    for(size_t k=0;k<4;k++)test_rate(rates[k]);
    test_original_grid_peak_distance();
    puts("periodic power-of-two resampling passed: zero, wrap tail, circular shift, mapping and original-grid peak distance at all rates");
    return 0;
}
