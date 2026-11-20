#include <assert.h>
#include <math.h>
#include <stddef.h>

#define CFO_COUNT 24
#define WIDE_REGIONAL_BINS 21

typedef struct {
    int folded_epoch;
    unsigned folded_masks[3];
    double frequencies[CFO_COUNT];
} leo_presence_workspace;

#include "wide_regional_cfo.h"
#include "folded_cfo_mask.h"

int main(void)
{
    leo_presence_workspace w={.folded_epoch=18,.folded_masks={0,4,32}};
    for(int f=0;f<WIDE_REGIONAL_BINS;++f)
        w.frequencies[f]=-800000.0+80000.0*f;
    assert(folded_epoch_mask(&w,17)==0);
    assert(folded_epoch_mask(&w,18)==4);
    assert(folded_epoch_mask(&w,19)==32);
    assert(folded_epoch_mask(&w,20)==0);

    const double period=10000000.0/44.0;
    const double phases[]={-period/2,-80000.0,-1234.0,0.0,124.0,80000.0,period/2};
    float x[88], a[44*CFO_COUNT], b[44*CFO_COUNT];
    for(int i=0;i<88;++i) x[i]=(float)((i*41)%77-38)*0.125f;
    for(int i=0;i<44*CFO_COUNT;++i) {
        a[i]=(float)((i*73)%43-21)*0.125f;
        b[i]=(float)((i*37)%67-33)*0.125f;
    }
    for(size_t trial=0;trial<sizeof(phases)/sizeof(phases[0]);++trial) {
        unsigned active=folded_cfo_mask(&w,phases[trial]), want=0;
        float exact[CFO_COUNT]={0}, restricted[CFO_COUNT]={0};
        for(int f=0;f<WIDE_REGIONAL_BINS;++f) {
            double delta=w.frequencies[f]-phases[trial];
            for(int alias=-4;alias<=4;++alias)
                if(fabs(delta-alias*period)<=80000.0) want|=1u<<f;
        }
        assert(active==want);
        assert(folded_cfo_count(active)>0 && folded_cfo_count(active)<WIDE_REGIONAL_BINS);
        wide_regional_float_add(x,a,b,44,0.6875f,exact);
        folded_cfo_float_add(x,a,b,44,0.6875f,restricted,active);
        for(int f=0;f<WIDE_REGIONAL_BINS;++f)
            assert(restricted[f]==((active&(1u<<f)) ? exact[f] : 0.0f));
    }
    return 0;
}
