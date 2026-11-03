#ifndef LEO_PROPOSAL_TRACKING_H
#define LEO_PROPOSAL_TRACKING_H
int leo_translate_center(int center,int from_window,int to_window,unsigned long rate,int n);
int leo_tracked_centers(const int left[4],int nl,const int right[4],int nr,int window,
    unsigned long rate,int n,int out[4],int *matches);
#endif
