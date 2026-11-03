#define _POSIX_C_SOURCE 200809L
#include "full_search.h"
#include <assert.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"

static size_t full_reference(const leo_presence_workspace *w,leo_full_search_peak *out)
{
    size_t nout=0;
    for(int f=0;f<11;++f)for(int e=0;e<(int)w->n;++e){double v=w->grid[f*w->n+e];
        double l=e?w->grid[f*w->n+e-1]:-INFINITY,r=e+1<(int)w->n?w->grid[f*w->n+e+1]:-INFINITY;
        if(v>=l&&v>=r&&(v>l||v>r))out[nout++]=(leo_full_search_peak){v,e,f};}
    return nout;
}
static void check(const int *active,int count,const double *values,int n)
{
    leo_presence_workspace w={0};w.n=(size_t)n;w.grid=calloc(11*(size_t)n,sizeof(*w.grid));assert(w.grid);
    for(int f=0;f<11;++f)for(int e=0;e<n;++e)w.grid[f*n+e]=-INFINITY;
    for(int f=0;f<11;++f)for(int i=0;i<count;++i)w.grid[f*n+active[i]]=values[(f*count+i)];
    leo_full_search_peak a[256],b[256];size_t na=collect_active_peaks(&w,active,count,a),nb=full_reference(&w,b);
    assert(na==nb&&!memcmp(a,b,na*sizeof(*a)));free(w.grid);
}
int main(void)
{
    int gaps[]={0,2,3,8,11};double values[55];for(int f=0;f<11;++f)for(int i=0;i<5;++i)values[f*5+i]=(double)((f+i)%3);
    check(gaps,5,values,12); /* boundaries, adjacent active cells, and gaps */
    int wrap[]={1,7};double equal[22];for(int i=0;i<22;++i)equal[i]=4;check(wrap,2,equal,9);
    int sparse[]={4};double neginf[11];for(int i=0;i<11;++i)neginf[i]=-INFINITY;check(sparse,1,neginf,10);
    for(int seed=0;seed<101;++seed){int active[17],n=0;double v[187];for(int e=0;e<31;++e)if(((seed*17+e*7)%5)==0)active[n++]=e;
        for(int i=0;i<11*n;++i) v[i]=(double)((seed+i*13)%7-3);
        check(active,n,v,31);
    }
    return 0;
}
