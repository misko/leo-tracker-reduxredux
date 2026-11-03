#define main proposal_probe_main
#include "proposal_probe.c"
#undef main
#include <assert.h>

static void check_close(float actual,float expected)
{
    float bound=4.0f*FLT_EPSILON*fmaxf(fabsf(expected),1.0f);
    if(!isfinite(actual)||fabsf(actual-expected)>bound)
        fprintf(stderr,"reciprocal mismatch actual=%.9g expected=%.9g bound=%.9g\n",actual,expected,bound);
    assert(isfinite(actual)&&fabsf(actual-expected)<=bound);
}

static void test_rate(size_t rate)
{
    size_t n=(rate+375)/750;
    fftwf_complex *candidate=fftwf_alloc_complex(n),*expected=fftwf_alloc_complex(n);
    int *support=malloc(n*sizeof(*support));assert(candidate&&expected&&support);
    float inverse[FRAMES+1]={0};for(int s=1;s<=FRAMES;++s)inverse[s]=1.0f/(float)s;
    for(size_t k=0;k<n;++k) {
        int s=(int)(k%(FRAMES+1));support[k]=s;
        float sign=k&1?-1.0f:1.0f;
        float real=s?sign*(float)s*2147352578.0f:0.0f;
        float imag=s?-sign*(float)s*1073676289.0f:0.0f;
        candidate[k][0]=expected[k][0]=real;candidate[k][1]=expected[k][1]=imag;
        if(s){expected[k][0]/=(float)s;expected[k][1]/=(float)s;}
    }
    normalize_fold(candidate,support,n,inverse);
    for(size_t k=0;k<n;++k){check_close(candidate[k][0],expected[k][0]);check_close(candidate[k][1],expected[k][1]);}
    size_t reduced=(n+LEO_PROPOSAL_DECIMATION-1)/LEO_PROPOSAL_DECIMATION;
    fftwf_complex *candidate_blocks=fftwf_alloc_complex(reduced),*expected_blocks=fftwf_alloc_complex(reduced);
    assert(candidate_blocks&&expected_blocks);
    block_average(candidate_blocks,candidate,n,LEO_PROPOSAL_DECIMATION);
    block_average(expected_blocks,expected,n,LEO_PROPOSAL_DECIMATION);
    for(size_t block=0;block<reduced;++block){
        size_t first=block*LEO_PROPOSAL_DECIMATION,last=first+LEO_PROPOSAL_DECIMATION;if(last>n)last=n;
        float scale=1.0f;for(size_t k=first;k<last;++k){scale=fmaxf(scale,fabsf(expected[k][0]));scale=fmaxf(scale,fabsf(expected[k][1]));}
        float bound=8.0f*FLT_EPSILON*scale;
        assert(fabsf(candidate_blocks[block][0]-expected_blocks[block][0])<=bound);
        assert(fabsf(candidate_blocks[block][1]-expected_blocks[block][1])<=bound);
    }
    fftwf_free(expected_blocks);fftwf_free(candidate_blocks);free(support);fftwf_free(expected);fftwf_free(candidate);
}

static void test_score_normalization(void)
{
    enum { N=65 };
    fftwf_complex reference[N],candidate[N],expected[N];
    for(int k=0;k<N;++k){reference[k][0]=(float)((k*13)%19-9);reference[k][1]=(float)((k*7)%17-8);candidate[k][0]=expected[k][0]=(float)(k%11-5)*16.0f;candidate[k][1]=expected[k][1]=(float)(k%7-3)*12.0f;}
    int support[N];float inverse[FRAMES+1]={0};for(int s=1;s<=FRAMES;++s)inverse[s]=1.0f/(float)s;
    for(int k=0;k<N;++k){support[k]=k%FRAMES+1;candidate[k][0]*=support[k];candidate[k][1]*=support[k];expected[k][0]*=support[k];expected[k][1]*=support[k];expected[k][0]/=support[k];expected[k][1]/=support[k];}
    normalize_fold(candidate,support,N,inverse);
    bank b;assert(!bank_init(&b,reference,N,2500000.0));
    block_average(b.time,candidate,N,b.decimation);correlate(&b,b.scores[0],0);
    float first[(N+3)/4];memcpy(first,b.scores[0],b.n*sizeof(*first));
    block_average(b.time,expected,N,b.decimation);correlate(&b,b.scores[0],0);
    for(size_t k=0;k<b.n;++k)assert(fabsf(first[k]-b.scores[0][k])<=2e-5f*fmaxf(1.0f,fabsf(b.scores[0][k])));
    bank_free(&b);
}

int main(void)
{
    assert(LEO_PROPOSAL_DECIMATION==4);
    const size_t rates[]={2500000,5000000,7500000,10000000};
    for(int k=0;k<4;++k)test_rate(rates[k]);
    test_score_normalization();
    puts("reciprocal normalization passed: support 0..16, extremes, partial blocks, score bound, all rates");
    return 0;
}
