#include "full_search.h"
#include <assert.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>


static const double CFO[11]={-400000,-320000,-240000,-160000,-80000,0,
    80000,160000,240000,320000,400000};

static const double *sort_cfo;
static int before(const leo_full_search_peak *a,const leo_full_search_peak *b)
{
    if(a->score!=b->score)return a->score>b->score?-1:1;
    double aa=fabs(sort_cfo[a->coarse_bin]),ab=fabs(sort_cfo[b->coarse_bin]);
    if(aa!=ab)return aa<ab?-1:1;
    return a->epoch<b->epoch?-1:a->epoch>b->epoch;
}
static size_t reference(leo_full_search_peak *p,size_t n,int32_t epochs,
    const double cfo[11],leo_full_search_peak out[8])
{
    sort_cfo=cfo;
    /* Stable insertion sort is intentionally independent of the new selector. */
    for(size_t i=1;i<n;++i){leo_full_search_peak v=p[i];size_t j=i;
        while(j&&before(&v,&p[j-1])<0){p[j]=p[j-1];--j;}p[j]=v;}
    size_t nr=0;
    for(size_t i=0;i<n&&nr<8;++i){int ok=1;for(size_t j=0;j<nr;++j){
        int d=abs(p[i].epoch-out[j].epoch);if(d>epochs-d)d=epochs-d;
        if(d<5&&fabs(cfo[p[i].coarse_bin]-cfo[out[j].coarse_bin])<=10000){ok=0;break;}
    }if(ok)out[nr++]=p[i];}return nr;
}
static void exhaustive_equivalence(void)
{
    /* Repeated deterministic mixes cover ties, wrapped epochs, adjacent CFOs,
       flat scores, and inventories above the eight-result limit. */
    for(int seed=0;seed<257;++seed){leo_full_search_peak a[121],b[121],x[8],y[8];
        for(int i=0;i<121;++i){unsigned v=(unsigned)(seed*1103515245u+i*12345u);
            a[i]=(leo_full_search_peak){(double)((v>>3)%7),(int32_t)(v%37),(int32_t)((v>>10)%11)};}
        memcpy(b,a,sizeof(a));size_t nx=leo_full_search_retain_peaks(a,121,37,CFO,x);
        size_t ny=reference(b,121,37,CFO,y);assert(nx==ny);assert(!memcmp(x,y,nx*sizeof(*x)));
    }
}

int main(void)
{
    exhaustive_equivalence();
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
