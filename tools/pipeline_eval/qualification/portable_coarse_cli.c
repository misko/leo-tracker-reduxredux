#define _POSIX_C_SOURCE 200809L
#include "../variants/portable_coarse.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

/* Stream fields are explicitly little-endian and never carry seed hints. */
enum { verify = 1, forced_mask = 2, max_groups = 4 };
_Static_assert(sizeof(PortableVerifierSeed)==24 && sizeof(PortableVerifierResult)==896,
               "unexpected native seed or verifier result ABI");

typedef struct {
    uint32_t lane, anchors, count;
    uint64_t coarse_cpu, coarse_wall, verify_cpu, verify_wall;
    PortableVerifierSeed seed[PORTABLE_VERIFIER_MAX_SEEDS];
    PortableCoarsePeak peak[PORTABLE_VERIFIER_MAX_SEEDS];
    PortableVerifierResult result[PORTABLE_VERIFIER_MAX_SEEDS];
    int positive;
} Group;

static void require(int ok,const char *message) {
    if (!ok) { fputs(message,stderr); fputc('\n',stderr); exit(2); }
}
static void take(FILE *stream,void *p,size_t n) {
    require(fread(p,1,n,stream)==n,"truncated raw coarse stream");
}
static void put(const void *p,size_t n) {
    require(fwrite(p,1,n,stdout)==n,"coarse output write failed");
}
static uint64_t ns(clockid_t clock) {
    struct timespec now;
    require(clock_gettime(clock,&now)==0,"clock read failed");
    return (uint64_t)now.tv_sec*UINT64_C(1000000000)+(uint64_t)now.tv_nsec;
}

static void run(Group *g, PortableCoarse *coarse, PortableVerifier *verifier,
                const int16_t *iq, PortableCoarseCapture *cfg, unsigned lane, unsigned anchors) {
    g->lane=lane;
    g->anchors=anchors;
    uint64_t wall=ns(CLOCK_MONOTONIC), cpu=ns(CLOCK_PROCESS_CPUTIME_ID);
    require(portable_coarse_acquire(coarse,iq,cfg,lane,anchors,g->seed,g->peak,&g->count)==0,
            "coarse raw geometry unsupported");
    g->coarse_cpu=ns(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    g->coarse_wall=ns(CLOCK_MONOTONIC)-wall;
    if (!verifier || !g->count) return;
    wall=ns(CLOCK_MONOTONIC); cpu=ns(CLOCK_PROCESS_CPUTIME_ID);
    require(portable_verifier_load(verifier,iq,lane)==0 &&
            portable_verifier_acquire(verifier,g->seed,g->count,cfg->center_hz[lane],cfg->low_hz,
                                      cfg->high_hz,g->result)==0,"verifier acquisition failed");
    for (unsigned i=0;i<g->count;++i) {
        PortableVerifierResult *r=&g->result[i];
        require(portable_verifier_glrt(verifier,g->seed[r->seed_index].epoch,r)==0,
                "verifier GLRT failed");
        if (r->flags&PORTABLE_VERIFIER_FRACTIONAL_GATE) g->positive=1;
    }
    g->verify_cpu=ns(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    g->verify_wall=ns(CLOCK_MONOTONIC)-wall;
}

int main(int argc,char **argv) {
    const uint32_t one=1;
    require(argc==2 && *(const unsigned char *)&one==1,"usage: portable-coarse raw-capture.bin");
    FILE *stream=fopen(argv[1],"rb");
    require(stream!=NULL,"cannot open raw coarse stream");
    char magic[8];
    uint32_t visits;
    take(stream,magic,sizeof(magic));
    take(stream,&visits,sizeof(visits));
    require(memcmp(magic,"LEOCOA01",8)==0 && visits && visits<=64,"bad raw coarse stream ABI");
    const size_t iq_bytes=4*PORTABLE_FINE_SAMPLES*sizeof(int16_t);
    int16_t *iq=malloc(iq_bytes);
    require(iq!=NULL,"raw input allocation failed");
    PortableCoarse *coarse=NULL;
    PortableVerifier *verifier=NULL;
    unsigned edge=2;
    uint64_t setup_cpu=0,setup_wall=0;
    put("LEOCOUT1",8); put(&visits,sizeof(visits));
    for (uint32_t v=0;v<visits;++v) {
        uint32_t field[5];
        double f[4];
        take(stream,field,sizeof(field)); take(stream,f,sizeof(f));
        PortableCoarseCapture cap={field[1],field[2],field[3],{f[0],f[1]},f[2],f[3]};
        require(cap.samples && cap.samples<=PORTABLE_FINE_SAMPLES && cap.edge<2 &&
                cap.lane_mask<=3 && (field[4]&~3u)==0 &&
                (!(field[4]&verify) || (field[4]==verify && cap.samples==PORTABLE_FINE_SAMPLES)),
                "invalid coarse capture header");
        take(stream,iq,4*cap.samples*sizeof(int16_t));
        if (edge!=cap.edge || ((field[4]&verify) && !verifier)) {
            portable_verifier_free(verifier); verifier=NULL;
            portable_coarse_free(coarse);
            const uint64_t wall=ns(CLOCK_MONOTONIC), cpu=ns(CLOCK_PROCESS_CPUTIME_ID);
            coarse=portable_coarse_create(cap.edge);
            if (coarse && (field[4]&verify))
                verifier=portable_verifier_create(portable_coarse_template(coarse,0),
                                                  portable_coarse_template(coarse,1));
            require(coarse && (!(field[4]&verify) || verifier),"workspace initialization failed");
            setup_cpu+=ns(CLOCK_PROCESS_CPUTIME_ID)-cpu;
            setup_wall+=ns(CLOCK_MONOTONIC)-wall;
            edge=cap.edge;
        }
        PortableVerifier *optional=(field[4]&verify) ? verifier : NULL;
        Group groups[max_groups]={0};
        unsigned count=0, positive=0, passed[2]={0};
        for (unsigned lane=0;lane<2;++lane) {
            if (!(cap.lane_mask&(1u<<lane))) continue;
            run(&groups[count],coarse,optional,iq,&cap,lane,PORTABLE_COARSE_PRIMARY);
            passed[lane]=(unsigned)groups[count].positive;
            positive+=passed[lane];
            ++count;
        }
        for (unsigned lane=0;lane<2;++lane) {
            if (!(cap.lane_mask&(1u<<lane))) continue;
            if ((field[4]&forced_mask) || (optional && positive && !passed[lane]))
                run(&groups[count++],coarse,optional,iq,&cap,lane,PORTABLE_COARSE_RETRY);
        }
        put(&field[0],sizeof(uint32_t)); put(&count,sizeof(count));
        for (unsigned j=0;j<count;++j) {
            Group *g=&groups[j];
            const uint32_t fields[]={g->lane,g->anchors,g->count};
            const uint64_t clocks[]={g->coarse_cpu,g->coarse_wall,g->verify_cpu,g->verify_wall};
            put(fields,sizeof(fields)); put(clocks,sizeof(clocks));
            for (unsigned i=0;i<g->count;++i) {
                put(&g->seed[i],sizeof(g->seed[i]));
                put(&g->peak[i].original_epoch,sizeof(unsigned));
                put(&g->peak[i].score,sizeof(double));
            }
            if (optional) put(g->result,g->count*sizeof(*g->result));
        }
    }
    require(fgetc(stream)==EOF && !ferror(stream) && fflush(stdout)==0,"unexpected trailing stream");
    struct rusage usage;
    require(getrusage(RUSAGE_SELF,&usage)==0,"RSS read failed");
    fprintf(stderr,"{\"setup_cpu_ns\":%" PRIu64 ",\"setup_wall_ns\":%" PRIu64
            ",\"peak_rss_kib\":%ld,\"coarse_workspace_bytes\":%zu,\"verifier_workspace_bytes\":%zu,"
            "\"input_bytes\":%zu}\n",setup_cpu,setup_wall,usage.ru_maxrss,
            portable_coarse_workspace_bytes(),portable_verifier_workspace_bytes(),iq_bytes);
    portable_verifier_free(verifier);
    portable_coarse_free(coarse);
    free(iq);
    fclose(stream);
    return 0;
}
