/* Component qualification only: paced SAVED IQ, no IIO or native port calls.
 * Reuse the actual live scan/order/retention helpers in their owning component.
 * Linking libiio satisfies the unused hardware entry point; it is never called. */
#define main unused_live_entry
#include "/home/mouse9911/gits/plutosdr-fw-radio20-tracking/tools/glrt_cpu_live_probe.c"
#undef main

static void *replay_worker(void *pointer)
{
    struct live *s=pointer;
    struct glrt_tracking_iq_view v;
    struct glrt_cpu_candidate candidate;
    double scores[8];unsigned selected;int rc=-1;
    uint64_t started=clock_ns(NULL),scanned=0,ranked=0;
    struct glrt_tracking_worker_config cfg={.owner=&s->owner,.references=s->refs,.fft=fft,.fft_context=s,
        .ports={s,clock_ns,cancelled,pause_worker,retain},.wall_budget_ns=UINT64_C(3000000000),
        .maximum_seed_age=2500000,.lead_samples=12500};
    s->attempts=1;
    if(glrt_tracking_iq_owner_copy(&s->owner,s->epoch,0,NULL,0,&v)) goto done;
    candidate=(struct glrt_cpu_candidate){.window_start=v.first,.epoch=s->epoch};
    cfg.source_deadline=candidate.window_start+5000000;
    if(glrt_tracking_iq_owner_copy(&s->owner,s->epoch,candidate.window_start,s->scan_iq,14000,&v) || scan(s)) goto done;
    scanned=clock_ns(NULL);
    if(rank_candidates(s,scores,&selected)) goto done;
    ranked=clock_ns(NULL);candidate.peak=s->coarse.peaks[selected];
    fprintf(s->journal,"{\"kind\":\"paced_scan\",\"window_start\":%" PRIu64
        ",\"scan_ms\":%.9g,\"rank_ms\":%.9g,\"selected_rank\":%u,\"peaks\":[",
        candidate.window_start,(scanned-started)/1e6,(ranked-scanned)/1e6,selected);
    for(unsigned k=0;k<s->coarse.count;k++) fprintf(s->journal,"%s[%u,%u,%u,%.17g]",k ? "," : "",
        s->coarse.peaks[k].epoch,s->coarse.peaks[k].frequency,s->coarse.peaks[k].score,scores[k]);
    fputs("]}\n",s->journal);
    if(fflush(s->journal) || fwrite(s->coarse.grid,sizeof(s->coarse.grid),1,s->grids)!=1 || fflush(s->grids)) goto done;
    /* Host tests can scan faster than four complete pilots arrive. Respect real pacing. */
    do {
        if(cancelled(s) || glrt_tracking_iq_owner_copy(&s->owner,s->epoch,0,NULL,0,&v) || v.closed) goto done;
        if(v.end>=candidate.window_start+17000) break;
        if(pause_worker(s)) goto done;
    } while(1);
    rc=glrt_tracking_worker_run_cpu(&s->worker,&cfg,&candidate);
done:
    fprintf(s->journal,"{\"kind\":\"paced_terminal\",\"worker_status\":%d,\"elapsed_ms\":%.9g,"
        "\"retained_past\":%u,\"supported_history\":%u,\"source\":",rc,(clock_ns(NULL)-started)/1e6,
        s->worker.retained_past,s->worker.live.core.trend.history.count);view(s->journal,&s->worker.checked_source);
    fputs("}\n",s->journal);
    if(ferror(s->journal) || fflush(s->journal)) rc=-1;
    if(rc==GLRT_WORKER_READY) {
        int observer_rc=start_observer(s);void *result=NULL;
        if(observer_rc) rc=observer_rc;
        else {
            /* Producer keeps publishing paced saved IQ. Let the actual live
             * observer reach its own finite terminal condition, then join it.
             * There is deliberately no native controller or RF in this replay. */
            if(pthread_join(s->observer_thread,&result)) _exit(2);
            s->observer_started=0;
            fprintf(s->journal,"{\"kind\":\"observer_join\",\"attempt\":1,\"episode\":0,\"epoch\":3,"
                "\"observer_result\":%d,\"observer_status\":%d,\"observer_joined\":1}\n",
                s->observer_result,s->observer_result);
            if(result || ferror(s->journal) || fflush(s->journal) ||
               (s->observer_result!=GLRT_OBSERVER_HISTORY && s->observer_result!=GLRT_OBSERVER_DONE)) rc=-1;
        }
    }
    if(pthread_mutex_lock(&s->mutex)) return (void *)(uintptr_t)1;
    s->result=rc;s->done=1;
    return (void *)(uintptr_t)(pthread_mutex_unlock(&s->mutex)!=0);
}

int main(int argc,char **argv)
{
    struct live *s=calloc(1,sizeof(*s));
    int16_t *ring=malloc(RING*4U),*input=malloc(6250000*4U);
    fftw_complex *bins=fftw_malloc(GLRT_RESOLVER_FFT*sizeof(*bins));
    uint64_t first,started,end,maximum_lag=0;char path[4096],*tail;int rc=0,done=0;
    if(argc!=6 || !s || !ring || !input || !bins) return 2;
    errno=0;first=strtoull(argv[4],&tail,10);
    if(errno || *tail || first>UINT64_MAX-6250000) return 2;
    if(load(argv[1],s->refs,sizeof(s->refs)) || load(argv[2],s->bank,sizeof(s->bank)) ||
       load(argv[3],input,6250000*4U)) return 2;
    s->epoch=3;s->rate=60000000;
    if(pthread_mutex_init(&s->mutex,NULL)) return 2;
    s->fft=fftw_plan_dft_1d(GLRT_RESOLVER_FFT,bins,bins,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
    if(!s->fft || glrt_tracking_iq_owner_init(&s->owner,ring,RING,s->epoch,first)) return 2;
    snprintf(path,sizeof(path),"%s/worker.jsonl",argv[5]);s->journal=fopen(path,"wx");
    snprintf(path,sizeof(path),"%s/worker.iq.ci16",argv[5]);s->worker_iq=fopen(path,"wbx");
    snprintf(path,sizeof(path),"%s/grids.u32",argv[5]);s->grids=fopen(path,"wbx");
    snprintf(path,sizeof(path),"%s/observer.jsonl",argv[5]);s->observer_journal=fopen(path,"wx");
    snprintf(path,sizeof(path),"%s/observer.iq.ci16",argv[5]);s->observer_iq=fopen(path,"wbx");
    if(!s->journal || !s->worker_iq || !s->grids || !s->observer_journal || !s->observer_iq) return 2;
    signal(SIGALRM,signal_stop);alarm(10);
    started=clock_ns(NULL);s->deadline_ns=started+UINT64_C(3000000000);end=first+14000;
    if(glrt_tracking_iq_owner_publish(&s->owner,s->epoch,first,input,14000,end,started) ||
       pthread_create(&s->thread,NULL,replay_worker,s)) return 2;
    while(!done) {
        uint64_t now=clock_ns(NULL),available=first+14000+(now-started)/400;
        struct timespec pause={0,100000};
        if(available>end && available-end>maximum_lag) maximum_lag=available-end;
        if(interrupted || now>=s->deadline_ns || available>first+6250000) { rc=1;break; }
        while(end+16384<=available) {
            if(glrt_tracking_iq_owner_publish(&s->owner,s->epoch,end,input+2*(end-first),16384,available,now))
                { rc=1;break; }
            end+=16384;
        }
        if(rc) break;
        if(pthread_mutex_lock(&s->mutex)) _exit(2);
        done=s->done;
        if(pthread_mutex_unlock(&s->mutex)) _exit(2);
        nanosleep(&pause,NULL);
    }
    if(rc) {
        if(pthread_mutex_lock(&s->mutex)) _exit(2);
        s->stop=1;
        if(pthread_mutex_unlock(&s->mutex)) _exit(2);
    }
    { void *result=NULL;if(pthread_join(s->thread,&result) || result) _exit(2); }
    if(s->observer_started) _exit(2);
    if(glrt_tracking_iq_owner_close(&s->owner,rc) || glrt_tracking_iq_owner_destroy(&s->owner)) rc=1;
    if(fclose(s->journal) || fclose(s->worker_iq) || fclose(s->grids)) rc=1;
    if(fclose(s->observer_journal) || fclose(s->observer_iq)) rc=1;
    printf("{\"scope\":\"paced_saved_iq_live_observer_no_radio_io\",\"worker_status\":%d,\"source_samples\":%" PRIu64
        ",\"elapsed_ms\":%.9g,\"maximum_publication_lag_samples\":%" PRIu64
        ",\"rf_samples\":0,\"native_jobs\":0,\"status\":%d,\"observer_status\":%d,\"observer_measurements\":%u}\n",s->result,end-first,
        (clock_ns(NULL)-started)/1e6,maximum_lag,rc,s->observer_result,s->observer.measurements);
    alarm(0);fftw_destroy_plan(s->fft);fftw_free(bins);free(ring);free(input);
    if(pthread_mutex_destroy(&s->mutex)) rc=1;
    free(s);return rc;
}
