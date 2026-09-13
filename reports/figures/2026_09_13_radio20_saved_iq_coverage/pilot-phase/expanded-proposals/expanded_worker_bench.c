/* Offline candidate injection: unchanged production resolver and worker. */
#define main original_bench_main
#include "/home/mouse9911/gits/plutosdr-fw-radio20-tracking/tools/glrt_cpu_tracking_bench.c"
#undef main
int main(int argc,char **argv)
{
    struct glrt_tracking_worker *worker=calloc(1,sizeof(*worker));
    int16_t *iq=malloc(RETAINED*4U),*storage=malloc(RETAINED*4U),*refs=malloc(105600);
    struct context ctx={0};
    fftw_complex *bins=fftw_malloc(GLRT_RESOLVER_FFT*sizeof(*bins));
    struct glrt_tracking_iq_owner owner={0};
    alarm(10);
    if(argc!=6 || !worker || !iq || !storage || !refs || !bins ||
       load(argv[1],iq,RETAINED*4U) || load(argv[2],refs,105600)) return 2;
    struct glrt_cpu_candidate candidate={0};
    candidate.epoch=1;
    candidate.peak.epoch=(unsigned)strtoul(argv[3],NULL,10);
    candidate.peak.frequency=(unsigned)strtoul(argv[4],NULL,10);
    candidate.peak.score=(unsigned)strtoul(argv[5],NULL,10);
    ctx.fft=fftw_plan_dft_1d(GLRT_RESOLVER_FFT,bins,bins,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
    if(!ctx.fft) return 2;
    ctx.deadline=clock_ns(NULL)+UINT64_C(8000000000);
    if(glrt_tracking_iq_owner_init(&owner,storage,RETAINED,1,0) ||
       glrt_tracking_iq_owner_publish(&owner,1,0,iq,RETAINED,RETAINED,clock_ns(NULL))) return 2;
    struct glrt_tracking_worker_config cfg={.owner=&owner,.references=refs,.fft=fft,.fft_context=&ctx,
        .ports={&ctx,clock_ns,cancelled,no_more_iq,retain},.source_deadline=5000000,
        .wall_budget_ns=UINT64_C(3000000000),.maximum_seed_age=2500000,.lead_samples=2500};
    int rc=glrt_tracking_worker_run_cpu(worker,&cfg,&candidate);
    printf("{\"kind\":\"terminal\",\"worker_result\":%d,\"retained_past\":%u,\"supported_history\":%u,\"waits\":%u,\"receiver_time\":\"frozen\"}\n",
        rc,worker->retained_past,worker->live.core.trend.history.count,worker->waits);
    if(glrt_tracking_iq_owner_close(&owner,0) || glrt_tracking_iq_owner_destroy(&owner) || fflush(stdout)) return 2;
    fftw_destroy_plan(ctx.fft);fftw_free(bins);free(worker);free(iq);free(storage);free(refs);
    return 0;
}
