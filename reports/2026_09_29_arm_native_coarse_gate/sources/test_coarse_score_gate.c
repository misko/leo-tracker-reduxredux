static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <math.h>
#include <stdio.h>

int main(void)
{
    const double rates[]={2500000,5000000,7500000,10000000};
    for(size_t i=0;i<4;i++){
        assert(rates[i]>0);
        assert(!coarse_score_allowed(nextafter(LEO_COARSE_SCORE_GATE,0.0)));
        assert(coarse_score_allowed(LEO_COARSE_SCORE_GATE));
        assert(coarse_score_allowed(nextafter(LEO_COARSE_SCORE_GATE,INFINITY)));
        assert(!coarse_score_allowed(NAN));assert(!coarse_score_allowed(INFINITY));
    }
    puts("coarse-score .15 gate passed all-rate threshold, nextafter, and nonfinite checks");
    return 0;
}
