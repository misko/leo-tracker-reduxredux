/* Test the private conditioned scorer: this includes the experiment TU so the
 * exact fallback and guarded-screen mechanics are exercised without exporting
 * a research-only API. */
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static leo_presence_workspace *workspace(int zero_template)
{
    const uint32_t rate=2500000;
    size_t n=(size_t)nearbyint(rate/750.0);
    leo_presence_complex *exact=calloc(n,sizeof(*exact));
    assert(exact);
    for (size_t k=0;k<n && !zero_template;++k) {
        exact[k].re=cos(.013*k); exact[k].im=sin(.013*k);
    }
    leo_presence_workspace *w=leo_presence_create(rate,exact,exact,n);
    free(exact); assert(w);
    return w;
}

static void fill(leo_presence_workspace *w, int zero)
{
    double phase_step=.013+TAU*1550.001/w->rate;
    for (size_t k=0;k<w->max_samples;++k) {
        w->samples[k]=zero ? 0 : (.5*cos(phase_step*k)+I*.5*sin(phase_step*k));
    }
}

int main(void)
{
    double regular[41], irregular[4]={-1350,-1225,-1090,-901};
    for (int j=0;j<41;++j) regular[j]=-2000+100*j;
    double a[41], b[41];

    leo_presence_workspace *w=workspace(0);
    fill(w,1);
    full_conditioned_scores(w,w->max_samples,0,regular,41,a,1);
    for (int j=0;j<41;++j) assert(a[j]==0 && isfinite(a[j]));

    fill(w,0);
    full_conditioned_scores(w,w->max_samples,0,irregular,4,a,1);
    full_conditioned_scores(w,w->max_samples,0,irregular,4,b,0);
    /* Bin zero is regular by definition and retains the original blocked-FP32
     * screen; each explicitly irregular bin follows the original FP64 path. */
    assert(fabs(a[0]-b[0])<=128.0*FLT_EPSILON);
    for (int j=1;j<4;++j) assert(a[j]==b[j]);

    /* Apply the production guard to a coherent near-tie and require its final
     * winner to equal the all-FP64 winner. */
    full_conditioned_scores(w,w->max_samples,0,regular,41,a,1);
    full_conditioned_scores(w,w->max_samples,0,regular,41,b,0);
    double maximum=a[best_frequency(a,regular,41)];
    const double guard=128.0*FLT_EPSILON;
    double second=-INFINITY;
    for (int j=0;j<41;++j) if (a[j]<maximum && a[j]>second) second=a[j];
    assert(maximum-second<=2*guard);
    int rechecked=0;
    for (int j=0;j<41;++j) {
        if (!isfinite(a[j]) || a[j]>=maximum-2*guard) {
            full_conditioned_scores(w,w->max_samples,0,regular+j,1,a+j,0);
            ++rechecked;
        } else a[j]=-INFINITY;
    }
    assert(rechecked>=2);
    assert(best_frequency(a,regular,41)==best_frequency(b,regular,41));
    leo_presence_destroy(w);

    w=workspace(1); fill(w,0);
    full_conditioned_scores(w,w->max_samples,0,regular,41,a,1);
    for (int j=0;j<41;++j) assert(a[j]==0 && isfinite(a[j]));
    leo_presence_destroy(w);
    puts("conditioned integration: zero energies, irregular fallback, guarded winner passed");
    return 0;
}
