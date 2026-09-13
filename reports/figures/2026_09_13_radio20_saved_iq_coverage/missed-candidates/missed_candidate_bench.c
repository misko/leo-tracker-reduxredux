/* Offline probe of a retained proposal. Receiver time is frozen; no RF ports. */
#define main original_bench_main
#include "/home/mouse9911/gits/plutosdr-fw-radio20-tracking/tools/glrt_cpu_tracking_bench.c"
#undef main
#include <math.h>
int main(int argc,char **argv)
{
    struct glrt_tracking_worker *worker=calloc(1,sizeof(*worker));
    struct glrt_cpu_coarse_workspace *coarse=calloc(1,sizeof(*coarse));
    int16_t *iq=malloc(RETAINED*4U),*storage=malloc(RETAINED*4U),*refs=malloc(105600);
    int16_t bank[12][11][11][2];struct context ctx={0};
    fftw_complex *bins=fftw_malloc(GLRT_RESOLVER_FFT*sizeof(*bins));
    struct glrt_tracking_iq_owner owner={0};double ranks[8]={0},energy=0;unsigned best=0;
    alarm(10);
    if(argc!=4 || !worker || !coarse || !iq || !storage || !refs || !bins ||
       load(argv[1],bank,sizeof(bank)) || load(argv[2],iq,RETAINED*4U) || load(argv[3],refs,105600)) return 2;
    ctx.fft=fftw_plan_dft_1d(GLRT_RESOLVER_FFT,bins,bins,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
    if(!ctx.fft) return 2;
    ctx.deadline=clock_ns(NULL)+UINT64_C(8000000000);
    if(glrt_tracking_iq_owner_init(&owner,storage,RETAINED,1,0) ||
       glrt_tracking_iq_owner_publish(&owner,1,0,iq,RETAINED,RETAINED,clock_ns(NULL)) ||
       search(coarse,iq,bank,&ctx) || !coarse->count) return 2;
    for(unsigned n=0;n<3300;n++) energy+=(double)refs[4*n]*refs[4*n]+(double)refs[4*n+1]*refs[4*n+1];
    for(unsigned k=0;k<coarse->count;k++) {
        double observed=0;unsigned first=coarse->peaks[k].epoch+22;
        memset(bins,0,GLRT_RESOLVER_FFT*sizeof(*bins));
        for(unsigned n=0;n<3300;n++) {
            double i=iq[2*(first+n)],q=iq[2*(first+n)+1],ri=refs[4*n],rq=refs[4*n+1];
            bins[n][0]=i*ri+q*rq;bins[n][1]=q*ri-i*rq;observed+=i*i+q*q;
        }
        fftw_execute(ctx.fft);
        for(unsigned n=0;n<GLRT_RESOLVER_FFT;n++) {
            double p=(bins[n][0]*bins[n][0]+bins[n][1]*bins[n][1])/fmax(observed*energy,1);
            if(p>ranks[k]) ranks[k]=p;
        }
        if(ranks[k]>ranks[best]) best=k;
    }
    printf("{\"kind\":\"proposal\",\"selected\":%u,\"rank_power\":%.17g,\"epoch\":%u}\n",best,ranks[best],coarse->peaks[best].epoch);
    struct glrt_cpu_candidate candidate={0,1,coarse->peaks[best]};
    struct glrt_tracking_worker_config cfg={.owner=&owner,.references=refs,.fft=fft,.fft_context=&ctx,
        .ports={&ctx,clock_ns,cancelled,no_more_iq,retain},.source_deadline=5000000,
        .wall_budget_ns=UINT64_C(3000000000),.maximum_seed_age=2500000,.lead_samples=2500};
    int rc=glrt_tracking_worker_run_cpu(worker,&cfg,&candidate);
    printf("{\"kind\":\"terminal\",\"worker_result\":%d,\"retained_past\":%u,\"supported_history\":%u,\"waits\":%u,\"receiver_time\":\"frozen\"}\n",
        rc,worker->retained_past,worker->live.core.trend.history.count,worker->waits);
    if(glrt_tracking_iq_owner_close(&owner,0) || glrt_tracking_iq_owner_destroy(&owner) || fflush(stdout)) return 2;
    fftw_destroy_plan(ctx.fft);fftw_free(bins);free(worker);free(coarse);free(iq);free(storage);free(refs);
    return 0;
}
