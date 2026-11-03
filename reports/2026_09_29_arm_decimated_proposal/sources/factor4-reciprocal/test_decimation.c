#define main proposal_probe_main
#include "proposal_probe.c"
#undef main
#include <assert.h>

static void test_partial_block(void)
{
    fftwf_complex input[5]={{1,10},{2,20},{3,30},{4,40},{5,50}},output[5]={{0}};
    block_average(output,input,5,LEO_PROPOSAL_DECIMATION);
    size_t blocks=(5u+LEO_PROPOSAL_DECIMATION-1u)/LEO_PROPOSAL_DECIMATION;
    for(size_t block=0;block<blocks;++block) {
        size_t first=block*LEO_PROPOSAL_DECIMATION,last=first+LEO_PROPOSAL_DECIMATION;
        if(last>5)last=5;
        float real=0,imag=0;for(size_t k=first;k<last;++k){real+=input[k][0];imag+=input[k][1];}
        assert(output[block][0]==real/(float)(last-first));
        assert(output[block][1]==imag/(float)(last-first));
    }
    if(LEO_PROPOSAL_DECIMATION>1) {
        assert(output[blocks-1][0]==5.0f);
        assert(output[blocks-1][1]==50.0f);
    }
}

static void test_original_grid_wrap(void)
{
    fftwf_complex t[5]={{1,2},{3,4},{5,6},{7,8},{9,10}},feature[5],reduced[5]={{0}};
    const int lag=3;
    for(size_t k=0;k<5;++k) {
        size_t q=(k+(size_t)lag)%5;
        float ar=t[q][0],ai=t[q][1],br=t[k][0],bi=t[k][1];
        feature[k][0]=ar*br+ai*bi;feature[k][1]=ai*br-ar*bi;
    }
    block_average(reduced,feature,5,LEO_PROPOSAL_DECIMATION);
    size_t last=(5u+LEO_PROPOSAL_DECIMATION-1u)/LEO_PROPOSAL_DECIMATION-1u;
    size_t first=last*LEO_PROPOSAL_DECIMATION,end=first+LEO_PROPOSAL_DECIMATION;if(end>5)end=5;
    float real=0,imag=0;for(size_t k=first;k<end;++k){real+=feature[k][0];imag+=feature[k][1];}
    assert(reduced[last][0]==real/(float)(end-first));
    assert(reduced[last][1]==imag/(float)(end-first));
}

static void test_mapping(void)
{
    bank b={.decimation=LEO_PROPOSAL_DECIMATION};
    for(int k=0;k<20;++k)assert(map_epoch(&b,k)==LEO_PROPOSAL_DECIMATION*k);
}

int main(void)
{
    assert(LEO_PROPOSAL_DECIMATION==1||LEO_PROPOSAL_DECIMATION==2||LEO_PROPOSAL_DECIMATION==4);
    test_partial_block();test_original_grid_wrap();test_mapping();
    printf("decimation passed: factor=%d, ceil length, partial weighting, original-grid wrap, epoch mapping\n",LEO_PROPOSAL_DECIMATION);
    return 0;
}
