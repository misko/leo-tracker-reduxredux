#include "proposal_tracking.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
int main(void){
    const unsigned long rates[]={2500000,5000000,7500000,10000000};
    for(int q=0;q<4;q++){unsigned long rate=rates[q];int n=(int)llround((double)rate/750.0);
        for(int k=0;k<n;k+=n/17){int odd=leo_translate_center(k,0,1,rate,n),back=leo_translate_center(odd,1,0,rate,n);assert(back==k||abs(back-k)==1||abs(back-k)==n-1);assert(odd>=0&&odd<n);}
        int left[4]={0,n/4,n/2,3*n/4},right[4],out[4],matches;
        for(int k=0;k<4;k++)right[k]=leo_translate_center(left[k],0,2,rate,n);
        int count=leo_tracked_centers(left,4,right,4,1,rate,n,out,&matches);assert(count==4&&matches==4);
        right[0]+=8;right[1]+=8;right[2]+=8;right[3]+=8;count=leo_tracked_centers(left,4,right,4,1,rate,n,out,&matches);assert(count==0&&matches<2);
    }
    puts("proposal tracking mapping: all rates, wrap, agreement, fallback passed");return 0;
}
