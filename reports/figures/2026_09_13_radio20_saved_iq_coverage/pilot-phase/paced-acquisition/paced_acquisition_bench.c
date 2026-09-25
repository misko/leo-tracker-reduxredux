/* Actual live kernels on paced saved IQ. No IIO or native ports are invoked. */
#define main unused_live_main
#include "/home/mouse9911/gits/plutosdr-fw-radio20-tracking/tools/glrt_cpu_live_probe.c"
#undef main
struct producer_context {
    struct live *live;
    const int16_t *iq;
    uint64_t count,origin;
    int result;
};
static void *produce_saved(void *pointer)
{
    struct producer_context *p=pointer;
    for(uint64_t at=14000;at<p->count;) {
        uint64_t n=p->count-at;if(n>CHUNK)n=CHUNK;
        uint64_t target=p->origin+(at+n-14000)*400;
        struct timespec t={(time_t)(target/1000000000),(long)(target%1000000000)};
        int rc;
        do { rc=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&t,NULL); } while(rc==EINTR);
        if(rc || glrt_tracking_iq_owner_publish(&p->live->owner,1,at,p->iq+2*at,n,at+n,clock_ns(NULL))) {
            p->result=-1;break;
        }
        at+=n;
    }
    return NULL;
}
int main(int argc,char **argv)
{
    if(argc!=6)return 2;
    unsigned cut=(unsigned)strtoul(argv[4],NULL,10);
    if(cut>3)return 2;
    alarm(10);
    struct live *s=calloc(1,sizeof(*s));
    int16_t *input=malloc(25000000),*ring=malloc(RING*4U);
    fftw_complex *bins=fftw_malloc(GLRT_RESOLVER_FFT*sizeof(*bins));
    char path[4096];pthread_t producer;double scores[64];unsigned selected;
    if(!s || !input || !ring || !bins || load(argv[1],input,25000000) ||
       load(argv[2],s->bank,sizeof(s->bank)) || load(argv[3],s->refs,sizeof(s->refs)))return 2;
    s->epoch=1;s->rate=60000000;s->attempts=s->attempt_limit=1;s->selected_iq=1;
    s->rank_budget=64;s->observer_spacing=3;
    if(pthread_mutex_init(&s->mutex,NULL))return 2;
    s->fft=fftw_plan_dft_1d(GLRT_RESOLVER_FFT,bins,bins,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
    s->ranking_fft=fftw_plan_dft_1d(4096,bins,bins,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
    if(!s->fft || !s->ranking_fft)return 2;
#define OPEN(field,name) do { if(snprintf(path,sizeof(path),"%s/%s",argv[5],name)<0 || !(s->field=fopen(path,"wbx")))return 2; } while(0)
    OPEN(journal,"worker.jsonl");OPEN(worker_iq,"worker.iq.ci16");
    OPEN(observer_journal,"observer.jsonl");OPEN(observer_iq,"observer.iq.ci16");
    uint64_t offset=(uint64_t)cut*447851;
    struct producer_context p={s,input+2*offset,6250000-offset,clock_ns(NULL),0};
    s->deadline_ns=p.origin+UINT64_C(5000000000);
    if(glrt_tracking_iq_owner_init(&s->owner,ring,RING,1,0) ||
       glrt_tracking_iq_owner_publish(&s->owner,1,0,p.iq,14000,14000,p.origin) ||
       pthread_create(&producer,NULL,produce_saved,&p))return 2;
    struct glrt_tracking_iq_view view;
    if(glrt_tracking_iq_owner_copy(&s->owner,1,0,s->scan_iq,14000,&view) || scan(s) ||
       rank_candidates(s,scores,&selected))return 2;
    uint64_t scan_done=clock_ns(NULL);
    struct glrt_cpu_candidate candidate={0,1,s->wide_peaks[selected]};
    struct glrt_tracking_worker_config cfg={.owner=&s->owner,.references=s->refs,.fft=fft,.fft_context=s,
        .ports={s,clock_ns,cancelled,pause_worker,retain},.wall_budget_ns=UINT64_C(3000000000),
        .maximum_seed_age=2500000,.lead_samples=12500,.source_deadline=5000000};
    int rc=glrt_tracking_worker_run_cpu(&s->worker,&cfg,&candidate);
    uint64_t worker_done=clock_ns(NULL);
    int observer_start=0;
    if(rc==GLRT_WORKER_READY) {
        observer_start=start_observer(s);
        if(!observer_start) {
            /* Natural observer completion, without native-controller authority. */
            if(pthread_join(s->observer_thread,NULL))return 2;
            s->observer_started=0;
            fprintf(s->journal,"{\"kind\":\"observer_join\",\"attempt\":1,\"observer_joined\":1,\"observer_status\":%d}\n",s->observer_result);
            if(fflush(s->journal))return 2;
        }
    }
    uint64_t observer_done=clock_ns(NULL);
    if(pthread_join(producer,NULL) || p.result || glrt_tracking_iq_owner_close(&s->owner,0) ||
       glrt_tracking_iq_owner_destroy(&s->owner))return 2;
    printf("{\"scope\":\"paced_saved_IQ_acquisition_and_observer\",\"new_rf_samples\":0,\"native_jobs\":0,\"cut\":%u,\"winner\":%u,\"rank_power\":%.17g,\"scan_ns\":%" PRIu64 ",\"worker_ns\":%" PRIu64 ",\"observer_ns\":%" PRIu64 ",\"worker_status\":%d,\"past\":%u,\"history_count\":%u,\"observer_start\":%d,\"observer_status\":%d,\"observer_measurements\":%u,\"producer_samples\":%" PRIu64 "}\n",
        cut,selected+1,scores[selected],scan_done-p.origin,worker_done-scan_done,observer_done-worker_done,
        rc,s->worker.retained_past,s->worker.live.core.trend.history.count,observer_start,s->observer_result,s->observer_retained,p.count);
    int failed=fclose(s->journal) || fclose(s->worker_iq) || fclose(s->observer_journal) || fclose(s->observer_iq);
    fftw_destroy_plan(s->fft);fftw_destroy_plan(s->ranking_fft);fftw_free(bins);
    pthread_mutex_destroy(&s->mutex);free(s);free(input);free(ring);alarm(0);
    return failed || fflush(stdout) ? 2 : 0;
}
