static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <math.h>
#include <stdio.h>

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    const double thresholds[]={.320,.150,.175,.152};
    for(size_t i=0;i<4;++i) {
        assert(coarse_score_threshold(rates[i])==thresholds[i]);
        assert(!coarse_score_allowed(rates[i],nextafter(thresholds[i],0.0)));
        assert(coarse_score_allowed(rates[i],thresholds[i]));
        assert(coarse_score_allowed(rates[i],nextafter(thresholds[i],INFINITY)));
        assert(!coarse_score_allowed(rates[i],NAN));
        assert(!coarse_score_allowed(rates[i],INFINITY));
    }
    assert(!coarse_score_allowed(123,NAN));
    puts("rate coarse gate passed all rates, equal/nextafter, and nonfinite checks");
    return 0;
}
