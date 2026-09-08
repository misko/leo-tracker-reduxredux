/* Bounded IPC qualification: ten zero probes, or repeated saved probes paced
 * at 126 ms (default) or 120 ms. Neither mode opens RF or replays a complete
 * recorded DMA stream. */
#define _GNU_SOURCE
#include "../../src/leo/scanner/native_presence/pool.h"
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>

static double now_ms(void)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC,&value)) return -1;
    return value.tv_sec*1000.0+value.tv_nsec/1000000.0;
}

static uint32_t decode32(const unsigned char *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }

static uint64_t decode64(const unsigned char *p)
{ return (uint64_t)decode32(p)|((uint64_t)decode32(p+4)<<32); }

static void doubles(const double *values, size_t count)
{
    putchar('[');
    for (size_t k=0;k<count;++k) printf("%s%.17g",k ? "," : "",values[k]);
    putchar(']');
}
static void integers(const uint32_t *values, size_t count)
{
    putchar('[');
    for (size_t k=0;k<count;++k) printf("%s%u",k ? "," : "",values[k]);
    putchar(']');
}

static void print_result(const leo_probe_result *r, unsigned probes, double latency)
{
    int dwell=r->request.sample_count==r->request.rate_hz/50*6;
    printf("{\"schema\":\"%s\",\"sequence\":%" PRIu64
        ",\"probe_index\":%" PRIu64 ",\"visit\":%" PRIu64 ",\"rate_hz\":%u,"
        "\"device_counter\":\"%" PRIu64 "\",\"edge\":%u,\"channel\":%u,\"status\":%d,"
        "\"total_cpu_ms\":%.9g,\"total_wall_ms\":%.9g,\"delivery_latency_ms\":%.9g,\"candidates\":[",
        dwell ? "native-worker-dwell-result-v1" : "native-worker-paced-result-v1",
        r->request.sequence,r->request.sequence%probes,r->request.visit,r->request.rate_hz,
        r->request.probe_start,r->request.edge,r->request.channel,r->status,
        dwell ? r->dwell.total_cpu_ms : r->evidence.total_cpu_ms,
        dwell ? r->dwell.total_wall_ms : r->evidence.total_wall_ms,latency);
    for (int j=0; j<r->evidence.candidate_count; ++j) {
        const leo_presence_candidate *c=&r->evidence.candidates[j];
        printf("%s{\"epoch\":%d,\"fractional_complete\":%d,\"fractional_offset_samples\":%.17g,"
            "\"acquired_cfo_hz\":%.17g,\"tracking_cfo_hz\":%.17g,\"exact_score\":%.17g,"
            "\"control_score\":%.17g,\"margin\":%.17g}",j ? ",":"",c->epoch,
            c->fractional_complete,c->fractional_offset_samples,c->acquired_cfo_hz,
            c->tracking_cfo_hz,c->exact_score,c->control_score,c->margin);
    }
    printf("],\"nuisance\":{\"enabled\":%d,\"applied\":%d,\"frequency_hz\":%.17g,"
        "\"spectral_fraction\":%.17g,\"fitted_power_fraction\":%.17g}",
        r->nuisance.enabled,r->nuisance.applied,r->nuisance.frequency_hz,
        r->nuisance.spectral_fraction,r->nuisance.fitted_power_fraction);
    if (dwell) {
        const leo_probe_dwell_evidence *d=&r->dwell;
        printf(",\"sample_count\":%u,\"valid_end\":\"%" PRIu64 "\",\"rx\":%u,"
            "\"search_window_mask\":%u,\"confirmation_window_mask\":%u,\"rank\":{\"scores\":",
            r->request.sample_count,r->request.valid_end,r->request.rx,
            d->search_window_mask,d->confirmation_window_mask);
        doubles(d->rank.scores,6);
        printf(",\"order\":"); integers(d->rank.order,6);
        printf(",\"projected_epoch_samples\":"); integers(d->rank.projected_epoch_samples,6);
        printf(",\"total_cpu_ms\":%.9g,\"total_wall_ms\":%.9g},"
            "\"confirmation_cpu_ms\":%.9g,\"confirmation_wall_ms\":%.9g,"
            "\"screen_diagnostics\":{\"available_mask\":%u,\"selected\":%u,\"contrast\":",
            d->rank.total_cpu_ms,d->rank.total_wall_ms,r->evidence.total_cpu_ms,r->evidence.total_wall_ms,
            d->screens.available_mask,d->screens.selected);
        doubles(d->screens.contrast,2);
        printf(",\"scores\":["); doubles(d->screens.scores[0],6); printf(","); doubles(d->screens.scores[1],6);
        printf("],\"order\":["); integers(d->screens.order[0],6); printf(","); integers(d->screens.order[1],6);
        printf("],\"epochs\":["); integers(d->screens.epochs[0],6); printf(","); integers(d->screens.epochs[1],6);
        printf("]}");
    }
    printf("}\n");
}

int main(int argc, char **argv)
{
    if (argc!=3 && argc!=5 && argc!=6) return 2;
    int paced=argc>=5, dwell=0;
    unsigned duration=0, arrival_period=126;
    if (argc==6) {
        if (!strcmp(argv[5],"120")) arrival_period=120;
        else if (strcmp(argv[5],"126")) return 2;
    }
    if (paced) {
        char *end; errno=0; long parsed=strtol(argv[4],&end,10);
        if (errno || !*argv[4] || *end || parsed<(long)arrival_period || parsed>300000) return 2;
        duration=(unsigned)parsed;
    }
    alarm(paced ? duration/1000+20 : 15);
    struct rlimit memory={192*1024*1024,192*1024*1024};
#if !defined(__SANITIZE_ADDRESS__)
    if (setrlimit(RLIMIT_AS,&memory)) return 2;
#else
    (void)memory;
#endif
    int status=2, shared=-1, templates=-1, notify[2]={-1,-1}, ready[2]={-1,-1};
    pid_t child=-1;
    leo_probe_pool *pool=MAP_FAILED;
    size_t pool_bytes=leo_probe_pool_bytes();
    int16_t *samples=NULL;
    uint64_t starts[96]={0}, visits[96]={0};
    uint32_t edges[96]={0}, channels[96]={0}, probe_count=1;
    double submitted_at[2500]={0};
    FILE *pack=NULL;
    const char *stage="open templates";
    unsigned char header[12];
    templates=open(argv[2],O_RDONLY);
    if (templates<0 || read(templates,header,12)!=12 || memcmp(header,"LPT1",4)) goto done;
    uint32_t rate=decode32(header+4);
    if (rate!=2500000 && rate!=5000000) goto done;
    if (paced) {
        stage="read bounded saved-probe pack";
        pack=fopen(argv[3],"rb");
        if (!pack || fread(header,1,12,pack)!=12 || decode32(header+4)!=rate) goto done;
        dwell=!memcmp(header,"LDP1",4);
        if (!dwell && memcmp(header,"LPP1",4)) goto done;
        probe_count=decode32(header+8);
        if (!probe_count || probe_count>(dwell ? 48u : 96u)) goto done;
    }
    size_t sample_count=rate/50*(dwell ? 6u : 1u);
    pool_bytes=dwell ? leo_dwell_pool_bytes() : leo_probe_pool_bytes();
    samples=calloc(sample_count*probe_count,2*sizeof(int16_t));
    if (!samples) goto done;
    if (paced) {
        for (uint32_t j=0; j<probe_count; ++j) {
            unsigned char record[24];
            if (fread(record,1,24,pack)!=24) goto done;
            starts[j]=decode64(record); visits[j]=decode64(record+8);
            edges[j]=decode32(record+16); channels[j]=decode32(record+20);
            if (edges[j]>1 || channels[j]<1 || channels[j]>4 || starts[j]>UINT64_MAX-rate*120/1000 ||
                fread(samples+(size_t)j*sample_count*2,4,sample_count,pack)!=sample_count) goto done;
        }
        if (fgetc(pack)!=EOF || ferror(pack)) goto done;
        fclose(pack); pack=NULL;
    }
    stage="create owned temporary mapping";
    char scratch[]="/tmp/leo-worker-smoke-XXXXXX";
    shared=mkstemp(scratch);
    if (shared<0) goto done;
    /* Only this just-created anonymous IPC backing file is unlinked. */
    if (unlink(scratch) || ftruncate(shared,(off_t)pool_bytes)) goto done;
    pool=mmap(NULL,pool_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,shared,0);
    if (pool==MAP_FAILED || (dwell ? leo_dwell_pool_init(pool,71,9,rate,1) : leo_probe_pool_init(pool,71,9,rate))) goto done;
    if (pipe2(notify,O_NONBLOCK) || pipe(ready)) goto done;
    char mapping_arg[32], notify_arg[32], templates_arg[32], parent_arg[32];
    snprintf(mapping_arg,sizeof(mapping_arg),"%d",shared);
    snprintf(notify_arg,sizeof(notify_arg),"%d",notify[0]);
    snprintf(templates_arg,sizeof(templates_arg),"%d",templates);
    snprintf(parent_arg,sizeof(parent_arg),"%ld",(long)getpid());
    char *arguments[]={argv[1],mapping_arg,notify_arg,templates_arg,parent_arg,NULL};
    stage="spawn isolated worker";
    child=fork();
    if (child<0) goto done;
    if (!child) {
        if (dup2(ready[1],STDOUT_FILENO)<0) _exit(2);
        execv(argv[1],arguments);
        _exit(2);
    }
    close(notify[0]); notify[0]=-1;
    close(ready[1]); ready[1]=-1;
    struct pollfd event={.fd=ready[0],.events=POLLIN};
    char handshake[6];
    if (poll(&event,1,5000)!=1 || read(ready[0],handshake,6)!=6 || memcmp(handshake,"ready\n",6)) goto done;
    stage="submit and recover bounded probes";
    leo_probe_collector collector={0};
    uint64_t jobs=paced ? (duration+arrival_period-1)/arrival_period : 10;
    uint64_t submitted=0, received=0, skipped=0;
    if (jobs>sizeof(submitted_at)/sizeof(submitted_at[0])) goto done;
    unsigned max_slots=0;
    double origin=now_ms(), max_lateness=0, max_copy=0;
    if (origin<0) goto done;
    while (received+skipped<jobs || (paced && now_ms()<origin+duration)) {
        double now=now_ms();
        if (now<0 || now>origin+(paced ? duration : 0)+5000) goto done;
        leo_probe_result result;
        while (leo_probe_read_result(pool,&result)==1) {
            uint64_t seq=result.request.sequence;
            if (seq>=submitted || result.status) goto done;
            if (!paced && (result.request.probe_start!=UINT64_C(10000000000000037)+seq*rate ||
                result.evidence.candidate_count || !result.nuisance.enabled || result.nuisance.applied)) goto done;
            if (paced) {
                print_result(&result,probe_count,now_ms()-submitted_at[seq]);
                /* A full scratch filesystem must fail qualification, not
                 * silently lose evidence while reporting successful work. */
                if (ferror(stdout)) { stage="write replay evidence"; goto done; }
            }
            ++received;
        }
        if (submitted>=jobs || (paced && now<origin+submitted*arrival_period) ||
            (!paced && received<submitted)) { usleep(500); continue; }
        uint64_t seq=submitted, index=seq%probe_count;
        uint64_t start=paced ? starts[index] : UINT64_C(10000000000000037)+seq*rate;
        leo_probe_request request={.session=71,.generation=9,.sequence=seq,.visit=paced ? visits[index] : seq,
            .valid_start=start,.valid_end=start+rate*120/1000,.probe_start=start,
            .rate_hz=rate,.sample_count=(uint32_t)sample_count,.rx=1,
            .channel=paced ? channels[index] : (uint32_t)(seq%4)+1,
            .edge=paced ? edges[index] : (uint32_t)(seq%2)};
        double copying=now_ms();
        int accepted=leo_probe_begin(&collector,pool,&request);
        if (accepted<0) goto done;
        submitted_at[seq]=copying;
        ++submitted;
        if (!accepted) { ++skipped; continue; }
        /* Full dwell submissions exercise block boundaries, but deliver their
         * chunks in a burst. This is not the original DMA/metadata timeline. */
        size_t block_size=dwell ? 32768 : sample_count;
        for (size_t offset=0;offset<sample_count;offset+=block_size) {
            size_t count=sample_count-offset<block_size ? sample_count-offset : block_size;
            int rc=leo_probe_feed(&collector,start+offset,samples+((size_t)index*sample_count+offset)*2,count,2,0);
            if (rc!=(offset+count==sample_count ? 1 : 0)) goto done;
        }
        double elapsed=now_ms()-copying;
        if (elapsed>max_copy) max_copy=elapsed;
        double lateness=copying-origin-seq*arrival_period;
        if (paced && lateness>max_lateness) max_lateness=lateness;
        if (write(notify[1],"1",1)!=1 && errno!=EAGAIN) goto done;
        leo_probe_stats current; leo_probe_pool_stats(pool,&current);
        if (current.occupied_slots>max_slots) max_slots=current.occupied_slots;
    }
    stage="EOF shutdown and accounting";
    close(notify[1]); notify[1]=-1;
    int child_status;
    if (waitpid(child,&child_status,0)!=child) goto done;
    child=-1;
    if (!WIFEXITED(child_status) || WEXITSTATUS(child_status)) goto done;
    leo_probe_stats stats; leo_probe_pool_stats(pool,&stats);
    if (stats.submitted!=jobs-skipped || stats.completed!=jobs-skipped || stats.busy!=skipped || stats.invalid || stats.aborted ||
        stats.result_dropped || stats.pending_results || stats.occupied_slots) goto done;
    printf("{\"schema\":\"%s\",\"rate_hz\":%u,"
        "\"submitted\":%u,\"completed\":%u,\"dropped\":%u,\"pool_bytes\":%zu,"
        "\"skipped\":%" PRIu64 ",\"duration_ms\":%u,\"elapsed_ms\":%.9g,\"max_occupied_slots\":%u,"
        "\"arrival_period_ms\":%u,"
        "\"max_submit_lateness_ms\":%.9g,\"max_copy_ms\":%.9g,"
        "\"scope\":\"%s; not RF or full archived-stream qualification\"}\n",
        dwell ? "native-worker-dwell-summary-v1" : (paced ? "native-worker-paced-summary-v1" : "native-worker-ipc-smoke-v1"),
        rate,stats.submitted,stats.completed,stats.result_dropped,pool_bytes,
        skipped,duration,now_ms()-origin,max_slots,arrival_period,max_lateness,max_copy,
        dwell ? "repeated 120ms saved dwells, 32768-sample chunks burst-delivered at the reported arrival period" :
            (paced ? "repeated saved probes at the reported arrival period" : "synthetic zero probes"));
    stage="flush replay evidence";
    if (fflush(stdout) || ferror(stdout)) goto done;
    status=0;
done:
    if (status) fprintf(stderr,"worker IPC smoke failed: %s\n",stage);
    if (child>0) {
        int child_status;
        pid_t state=waitpid(child,&child_status,WNOHANG);
        if (state==0) { kill(child,SIGKILL); waitpid(child,&child_status,0); }
    }
    free(samples);
    if (pack) fclose(pack);
    if (pool!=MAP_FAILED) munmap(pool,pool_bytes);
    if (shared>=0) close(shared);
    if (templates>=0) close(templates);
    for (int k=0; k<2; ++k) { if (notify[k]>=0) close(notify[k]); if (ready[k]>=0) close(ready[k]); }
    return status;
}
