#include "full_search.h"
#include <assert.h>

static const double CFO[11]={-400000,-320000,-240000,-160000,-80000,0,
    80000,160000,240000,320000,400000};

int main(void)
{
    leo_full_search_peak peaks[12]={
        {9,10,5},{10,10,5},{8,12,5},{7,14,5},
        {6,10,6},{5,20,5},{4,30,5},{3,40,5},
        {2,50,5},{1,60,5},{10,9,4},{10,8,6},
    }, retained[8];
    size_t n=leo_full_search_retain_peaks(peaks,12,100,CFO,retained);
    assert(n==8);
    /* Equal scores prefer the lowest absolute CFO, then lowest epoch. */
    assert(retained[0].coarse_bin==5 && retained[0].epoch==10);
    /* Same basin candidates at epochs 12 and 14 were compared with retained[0]. */
    for (size_t i=0;i<n;++i)
        assert(!(retained[i].coarse_bin==5 &&
            (retained[i].epoch==12 || retained[i].epoch==14)));

    leo_full_search_peak all_previous[4]={{10,0,5},{9,20,5},{8,23,5},{7,40,5}};
    n=leo_full_search_retain_peaks(all_previous,4,100,CFO,retained);
    assert(n==3);
    assert(retained[0].epoch==0 && retained[1].epoch==20 && retained[2].epoch==40);

    leo_full_search_peak seam[3]={{3,0,5},{2,98,5},{1,10,5}};
    n=leo_full_search_retain_peaks(seam,3,100,CFO,retained);
    assert(n==2 && retained[0].epoch==0 && retained[1].epoch==10);

    /* Python's stable sort preserves the original CFO-bin scan order when
     * score, absolute CFO, and epoch all tie. The first item then suppresses
     * the opposite-sign CFO when their separation threshold includes it. */
    const double CLOSE_CFO[11]={-40000,-30000,-20000,-10000,-5000,0,
        5000,10000,20000,30000,40000};
    leo_full_search_peak stable_ties[3]={{5,25,4},{5,25,6},{4,40,5}};
    n=leo_full_search_retain_peaks(stable_ties,3,100,CLOSE_CFO,retained);
    assert(n==2);
    assert(retained[0].coarse_bin==4 && retained[0].epoch==25);
    assert(retained[1].coarse_bin==5 && retained[1].epoch==40);
    return 0;
}
