#include "endpoint.h"
#include <float.h>
#include <math.h>
#include <string.h>

double leo_endpoint_wrap(uint32_t rate, double epoch)
{
    /* Work in exact 1/750-frame turns. This avoids pretending that a frame
     * is a repeatedly rounded integer number of samples. */
    double turns=fmod(epoch*750.0,(double)rate);
    if(turns<0) turns+=rate;
    return turns/750.0;
}

static double circular_delta(uint32_t rate,double a,double b)
{
    return remainder((b-a)*750.0,(double)rate)/750.0;
}

double leo_endpoint_interpolate_epoch(uint32_t rate,double left,double right,int window)
{
    /* The first endpoint is the unwrap anchor; the right phase is represented
     * by the nearest physical frame alias before linear interpolation. Convert
     * that absolute phase back to the current window's local coordinate. */
    double absolute=left+(window/10.0)*circular_delta(rate,left,right);
    return leo_endpoint_wrap(rate,absolute-window*(double)rate/100.0);
}

double leo_endpoint_project_constant(uint32_t rate,double endpoint,int window)
{
    return leo_endpoint_wrap(rate,endpoint-window*(double)rate/100.0);
}

int leo_endpoint_execution_window(int position)
{
    static const int order[11]={0,10,1,2,3,4,5,6,7,8,9};
    return position>=0&&position<11?order[position]:-1;
}

double leo_endpoint_acquisition_anchor(double tracking_cfo_hz)
{
    if(!isfinite(tracking_cfo_hz))return tracking_cfo_hz;
    return fmax(-400000.0,fmin(400000.0,tracking_cfo_hz));
}

typedef struct { int count; double cost; int choice[LEO_ENDPOINT_MAX]; } solution;

static int lex_less(const int *a,const int *b,int n)
{
    for(int i=0;i<n;i++) if(a[i]!=b[i]) return a[i]<b[i];
    return 0;
}

static void assign_rec(int i,int nl,int nr,const double edge[8][8],int used,
    int count,double cost,int choice[8],solution *best)
{
    if(i==nl) {
        if(count>best->count || (count==best->count &&
            (cost<best->cost-1e-15 || (fabs(cost-best->cost)<=1e-15 &&
             lex_less(choice,best->choice,nl))))) {
            best->count=count;best->cost=cost;memcpy(best->choice,choice,nl*sizeof(*choice));
        }
        return;
    }
    choice[i]=nr; assign_rec(i+1,nl,nr,edge,used,count,cost,choice,best);
    for(int j=0;j<nr;j++) if(!(used&(1<<j)) && isfinite(edge[i][j])) {
        choice[i]=j;assign_rec(i+1,nl,nr,edge,used|(1<<j),count+1,cost+edge[i][j],choice,best);
    }
}

int leo_endpoint_associate(uint32_t rate,const leo_full_search_result *left,
    const leo_full_search_result *right,leo_endpoint_association *out)
{
    if(!out||!left||!right||!rate||left->candidate_count<0||left->candidate_count>8||
       right->candidate_count<0||right->candidate_count>8) return -1;
    double edge[8][8];
    for(int i=0;i<left->candidate_count;i++) for(int j=0;j<right->candidate_count;j++) {
        double dt=fabs(circular_delta(rate,left->candidates[i].candidate.epoch,
            right->candidates[j].candidate.epoch));
        double df=fabs(left->candidates[i].candidate.tracking_cfo_hz-
            right->candidates[j].candidate.tracking_cfo_hz);
        edge[i][j]=(dt<=8&&df<=8000)?dt/8+df/8000:INFINITY;
    }
    solution best={-1,DBL_MAX,{0}}; int choice[8]={0};
    assign_rec(0,left->candidate_count,right->candidate_count,edge,0,0,0,choice,&best);
    memset(out,0,sizeof(*out)); int matched_right=0;
    for(int i=0;i<left->candidate_count;i++) if(best.choice[i]<right->candidate_count) {
        int j=best.choice[i]; leo_endpoint_pair *p=&out->pairs[out->pair_count++];
        p->left=i;p->right=j;p->timing_delta=circular_delta(rate,
            left->candidates[i].candidate.epoch,right->candidates[j].candidate.epoch);
        p->cost=edge[i][j];matched_right|=1<<j;
    } else out->left_unmatched[out->left_unmatched_count++]=i;
    for(int j=0;j<right->candidate_count;j++) if(!(matched_right&(1<<j)))
        out->right_unmatched[out->right_unmatched_count++]=j;
    return 0;
}
