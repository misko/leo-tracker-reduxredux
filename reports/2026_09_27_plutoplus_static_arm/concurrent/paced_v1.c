/* Persistent, bounded, saved-IQ workload. Scientific kernel is unchanged. */
#define main original_probe_main
#include "probe.c"
#undef main

typedef struct { mapped_file raw; char id[160]; unsigned context; } input_case;
typedef struct { char exact_path[256]; mapped_file exact, control; probe_work work; } context;

static void sleep_until(double ms)
{
    struct timespec t = {(time_t)(ms / 1000), (long)(fmod(ms,1000)*1000000)};
    int rc; do { rc=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&t,NULL); } while(rc==EINTR);
    if(rc) exit(2);
}

int main(int argc, char **argv)
{
    if(argc!=7) { fprintf(stderr,"usage: paced CASE_LIST RATE JOBS PERIOD_MS CORE RX_COUNT\n"); return 2; }
    unsigned rate=(unsigned)strtoul(argv[2],NULL,10), jobs=(unsigned)strtoul(argv[3],NULL,10);
    double period=strtod(argv[4],NULL); int core=atoi(argv[5]), receivers=atoi(argv[6]);
    if((rate!=2500000 && rate!=5000000 && rate!=7500000 && rate!=10000000) ||
       jobs<1 || jobs>600 || period<120 || period>1000 || jobs*period>90000 ||
       core<0 || core>=CPU_SETSIZE || (receivers!=1 && receivers!=2)) return 2;
    alarm(120);
    cpu_set_t cpus; CPU_ZERO(&cpus); CPU_SET(core,&cpus);
    if(sched_setaffinity(0,sizeof(cpus),&cpus) || sched_getaffinity(0,sizeof(cpus),&cpus) ||
       CPU_COUNT(&cpus)!=1 || !CPU_ISSET(core,&cpus)) { perror("affinity"); return 2; }
    input_case cases[32]={0}; context ctx[2]={0}; unsigned nc=0,nctx=0;
    size_t count=(size_t)rate*120/1000;
    FILE *f=fopen(argv[1],"r"); if(!f) return 2;
    char raw[256],exact[256],control[256],id[160];
    while(fscanf(f,"%255s %255s %255s %159s",raw,exact,control,id)==4) {
        if(nc==32) return 2;
        unsigned ci=0; while(ci<nctx && strcmp(exact,ctx[ci].exact_path)) ++ci;
        if(ci==nctx) {
            if(nctx==2) return 2;
            context *c=&ctx[nctx++]; strcpy(c->exact_path,exact);
            if(map_read(exact,&c->exact) || map_read(control,&c->control) ||
               c->exact.size!=c->control.size || c->exact.size%sizeof(leo_presence_complex)) return 2;
            for(int rx=0;rx<receivers;++rx) {
                c->work.work[rx]=leo_blind_aligned_v5_create(rate,c->exact.data,c->control.data,
                    c->exact.size/sizeof(leo_presence_complex),512,0);
                if(!c->work.work[rx]) return 2;
            }
        }
        input_case *c=&cases[nc++]; c->context=ci; strcpy(c->id,id);
        if(map_read(raw,&c->raw) || c->raw.size!=count*8) return 2;
        volatile uint8_t touch=0;
        for(size_t k=0;k<c->raw.size;k+=4096) touch^=((uint8_t*)c->raw.data)[k];
        (void)touch;
        for(int rx=0;rx<receivers;++rx) {
            leo_presence_dwell_result d={0}; leo_presence_rank_screens s={0}; double a,b,cpu,wall;
            if(run_rx(&ctx[ci].work,c->raw.data,count,(unsigned)rx,&d,&s,&a,&b,&cpu,&wall)) return 2;
        }
    }
    fclose(f); if(!nc) return 2;
    double epoch=millis(CLOCK_MONOTONIC)+1000;
    printf("{\"type\":\"ready\",\"pid\":%ld,\"core\":%d,\"rate_hz\":%u,\"jobs\":%u,\"period_ms\":%.9g,\"receivers\":%d,\"cases\":%u,\"epoch_ms\":%.9f}\n",
        (long)getpid(),core,rate,jobs,period,receivers,nc,epoch); fflush(stdout);
    for(unsigned j=0;j<jobs;++j) {
        double due=epoch+j*period; sleep_until(due);
        input_case *c=&cases[j%nc];
        double start=millis(CLOCK_MONOTONIC),cpu=millis(CLOCK_PROCESS_CPUTIME_ID);
        leo_presence_dwell_result d[2]={0}; leo_presence_rank_screens s[2]={0};
        double pc[2],pw[2],dc[2],dw[2];
        for(int rx=0;rx<receivers;++rx)
            if(run_rx(&ctx[c->context].work,c->raw.data,count,(unsigned)rx,&d[rx],&s[rx],&pc[rx],&pw[rx],&dc[rx],&dw[rx])) return 2;
        double end=millis(CLOCK_MONOTONIC),used=millis(CLOCK_PROCESS_CPUTIME_ID)-cpu;
        printf("{\"type\":\"visit\",\"index\":%u,\"case_id\":\"%s\",\"due_ms\":%.9f,\"start_ms\":%.9f,\"end_ms\":%.9f,\"cpu_ms\":%.9f,\"wall_ms\":%.9f,\"queue_ms\":%.9f,\"response_ms\":%.9f,\"receivers\":[",
            j,c->id,due,start,end,used,end-start,start-due,end-due);
        for(int rx=0;rx<receivers;++rx) {
            printf("%s{\"receiver\":%d,\"result\":",rx?",":"",rx);
            json_dwell(&d[rx]); printf(",\"screens\":"); json_screens(&s[rx]); putchar('}');
        }
        printf("]}\n"); fflush(stdout);
        double published=millis(CLOCK_MONOTONIC),service_cpu=millis(CLOCK_PROCESS_CPUTIME_ID)-cpu;
        printf("{\"type\":\"published\",\"index\":%u,\"end_ms\":%.9f,\"response_ms\":%.9f,\"service_cpu_ms\":%.9f}\n",j,published,published-due,service_cpu);
    }
    printf("{\"type\":\"complete\",\"jobs\":%u,\"end_ms\":%.9f}\n",jobs,millis(CLOCK_MONOTONIC));
    for(unsigned i=0;i<nc;++i) unmap_file(&cases[i].raw);
    for(unsigned i=0;i<nctx;++i) {
        for(int rx=0;rx<receivers;++rx) leo_blind_aligned_v5_destroy(ctx[i].work.work[rx]);
        unmap_file(&ctx[i].exact); unmap_file(&ctx[i].control);
    }
    return 0;
}
