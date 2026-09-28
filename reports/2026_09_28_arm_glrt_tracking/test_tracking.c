#include "track.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static int32_t reference_propagate(uint32_t rate,int32_t epoch)
{
    double period=(double)rate/750.0;
    double phase=fmod(epoch-(double)rate/100.0,period);
    if(phase<0)phase+=period;
    int32_t value=(int32_t)llround(phase),n=(int32_t)llround(period);
    return value==n?0:value;
}

static void test_propagation(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(size_t r=0;r<4;++r){
        int32_t n=(int32_t)llround((double)rates[r]/750.0);
        int32_t epochs[]={0,1,n/2,n-2,n-1};
        for(size_t i=0;i<5;++i)
            assert(leo_tracking_propagate_epoch(rates[r],epochs[i])==
                reference_propagate(rates[r],epochs[i]));
    }
}

static void test_wrapping(void)
{
    assert(leo_tracking_wrap_epoch(0,-1,3333)==3332);
    assert(leo_tracking_wrap_epoch(3332,1,3333)==0);
    assert(leo_tracking_wrap_epoch(2,-1,3333)==1);
    assert(leo_tracking_wrap_epoch(2,1,3333)==3);
    assert(leo_tracking_wrap_epoch(0,0,0)==-1);
}

static void test_state_isolation(void)
{
    leo_tracking_state rx[2];
    leo_tracking_state_reset(&rx[0]);leo_tracking_state_reset(&rx[1]);
    leo_tracking_candidate a[2]={{.seed_rank=0,.epoch=7,.acquired_cfo_hz=125},
        {.seed_rank=1,.epoch=9,.acquired_cfo_hz=-250}};
    leo_tracking_candidate b={.seed_rank=0,.epoch=99,.acquired_cfo_hz=500};
    assert(!leo_tracking_state_set(&rx[0],a,2));
    leo_tracking_state snapshot=rx[0];
    assert(!leo_tracking_state_set(&rx[1],&b,1));
    assert(!memcmp(&rx[0],&snapshot,sizeof(snapshot)));
    assert(rx[1].candidate_count==1&&rx[1].candidates[0].epoch==99);
    a[0].epoch=1000;
    assert(rx[0].candidates[0].epoch==7); /* state owns a stable copy */
    assert(leo_tracking_state_set(&rx[0],a,LEO_TRACK_MAX_CANDIDATES+1)==-1);
}

int main(void)
{
    test_propagation();test_wrapping();test_state_isolation();
    puts("tracking unit tests passed");return 0;
}
