#include "proposal_tracking.h"
#include <math.h>
#include <stdlib.h>
#ifndef LEO_TRACK_MIN_MATCHES
#define LEO_TRACK_MIN_MATCHES 2
#endif
static int distance(int a,int b,int n){int d=abs(a-b);return d<n-d?d:n-d;}
int leo_translate_center(int center,int from_window,int to_window,unsigned long rate,int n){
    long double period=(long double)rate/750.0L;
    long double absolute=(long double)center+(long double)(from_window-to_window)*(long double)(rate/100);
    long double phase=fmodl(absolute,period);if(phase<0)phase+=period;
    int mapped=(int)llroundl(phase*(long double)n/period);return mapped==n?0:mapped;
}
int leo_tracked_centers(const int left[4],int nl,const int right[4],int nr,int window,
    unsigned long rate,int n,int out[4],int *matches){
    int l[4],r[4],used[4]={0},count=0;*matches=0;
    for(int i=0;i<nl;i++)l[i]=leo_translate_center(left[i],window-1,window,rate,n);
    for(int i=0;i<nr;i++)r[i]=leo_translate_center(right[i],window+1,window,rate,n);
    for(int i=0;i<nl&&count<4;i++){int best=-1,bd=5;for(int j=0;j<nr;j++)if(!used[j]){int d=distance(l[i],r[j],n);if(d<bd){bd=d;best=j;}}
        if(best>=0){used[best]=1;(*matches)++;out[count++]=l[i];}}
    if(*matches<LEO_TRACK_MIN_MATCHES)return 0;
    for(int side=0;side<2&&count<4;side++)for(int i=0;i<(side?nr:nl)&&count<4;i++){int v=side?r[i]:l[i],near=0;for(int j=0;j<count;j++)if(distance(v,out[j],n)<5){near=1;break;}if(!near)out[count++]=v;}
    return count;
}
