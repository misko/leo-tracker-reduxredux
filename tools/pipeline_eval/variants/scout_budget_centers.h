/* Select the original distinct epoch basins from a longer prefix of the
 * combined rank surface. The stable radix sort orders increasing scores. */
#ifndef LEO_SCOUT_BUDGET_CENTERS_H
#define LEO_SCOUT_BUDGET_CENTERS_H

static int scout_budget_centers(const float *s,size_t fft_n,size_t n,int out[16],
    ranked *work,ranked *scratch)
{
    size_t count=0;
    for(size_t k=0;k<fft_n;++k){
        size_t left=k?k-1:fft_n-1,right=k+1==fft_n?0:k+1;
        if(s[k]>0&&s[k]>=s[left]&&s[k]>=s[right]&&(s[k]>s[left]||s[k]>s[right]))
            work[count++]=(ranked){s[k],(int)k};
    }
    if(!count)return 0;
    ranked *ordered=rank_radix(work,scratch,count);
    int used=0;
    while(count&&used<16){
        size_t first=count-1;
        while(first&&ordered[first-1].score==ordered[count-1].score)--first;
        /* Highest score group first, lower FFT bin first within ties. */
        for(size_t q=first;q<count&&used<16;++q){
            int epoch=(int)map_fft_index((size_t)ordered[q].index,n,fft_n),near=0;
            for(int j=0;j<used;++j){
                int gap=abs(epoch-out[j]);
                if(gap>(int)n-gap)gap=(int)n-gap;
                if(gap<5){near=1;break;}
            }
            if(!near)out[used++]=epoch;
        }
        count=first;
    }
    return used;
}

#endif
