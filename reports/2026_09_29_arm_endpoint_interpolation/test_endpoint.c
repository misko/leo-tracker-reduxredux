#include "endpoint.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static leo_full_search_candidate c(double epoch,double cfo)
{ leo_full_search_candidate x={0};x.candidate.epoch=(int)epoch;x.candidate.tracking_cfo_hz=cfo;return x; }

int main(void)
{
    const int order[]={0,10,1,2,3,4,5,6,7,8,9};
    for(int k=0;k<11;k++)assert(leo_endpoint_execution_window(k)==order[k]);
    assert(leo_endpoint_execution_window(-1)==-1&&leo_endpoint_execution_window(11)==-1);
    assert(leo_endpoint_acquisition_anchor(410000)==400000);
    assert(leo_endpoint_acquisition_anchor(-410000)==-400000);
    assert(leo_endpoint_acquisition_anchor(1234.5)==1234.5);
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int r=0;r<4;r++) {
        double period=rates[r]/750.0,left=period-3,right=4;
        assert(fabs(leo_endpoint_interpolate_epoch(rates[r],left,right,0)-left)<1e-9);
        assert(fabs(leo_endpoint_interpolate_epoch(rates[r],left,right,10)-right)<1e-9);
        assert(fabs(leo_endpoint_interpolate_epoch(rates[r],left,right,5)-(.5+period/2))<1e-8);
        assert(fabs(leo_endpoint_interpolate_epoch(rates[r],left,right,2)-
            leo_endpoint_wrap(rates[r],left+.2*7))<1e-8);
        assert(fabs(leo_endpoint_interpolate_epoch(rates[r],0,0,1)-period/2)<1e-8);
        assert(fabs(leo_endpoint_interpolate_epoch(rates[r],0,0,2))<1e-8);
        assert(fabs(leo_endpoint_interpolate_epoch(rates[r],7,7,1)-(period/2+7))<1e-8);
        assert(fabs(leo_endpoint_interpolate_epoch(rates[r],7,7,2)-7)<1e-8);
        assert(fabs(leo_endpoint_interpolate_epoch(rates[r],-3,4,5)-
            (period/2+.5))<1e-8);
        assert(fabs(leo_endpoint_project_constant(rates[r],0,1)-period/2)<1e-8);
        assert(fabs(leo_endpoint_project_constant(rates[r],0,2))<1e-8);
        double negative=leo_endpoint_wrap(rates[r],-3);
        assert(fabs(leo_endpoint_project_constant(rates[r],negative,1)-(period/2-3))<1e-8);
        assert(fabs(leo_endpoint_project_constant(rates[r],negative,2)-negative)<1e-8);
    }
    leo_full_search_result a={0},b={0};leo_endpoint_association x;
    assert(!leo_endpoint_associate(7500000,&a,&b,&x)&&x.pair_count==0);
    a.candidate_count=b.candidate_count=3;
    a.candidates[0]=c(10,1000);a.candidates[1]=c(10,1000);a.candidates[2]=c(400,30000);
    b.candidates[0]=c(11,1001);b.candidates[1]=c(11,1001);b.candidates[2]=c(900,-30000);
    assert(!leo_endpoint_associate(7500000,&a,&b,&x));
    assert(x.pair_count==2&&x.left_unmatched_count==1&&x.right_unmatched_count==1);
    assert(x.pairs[0].left==0&&x.pairs[0].right==0&&x.pairs[1].left==1&&x.pairs[1].right==1);
    puts("endpoint interpolation unit tests passed");
}
