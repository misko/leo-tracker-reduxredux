/* Saved RX1 IQ through the public SDK only. No IIO, RF, or transport daemon.
 * RX0 and the 1ms transition padding are explicitly SYNTHETIC sentinels.
 * Original source counters remain in LDP1; replay counters/timing are modeled. */
#define _POSIX_C_SOURCE 200809L
#include "../src/leo/scanner/native_presence/scanner_glrt.h"
#include "../src/leo/scanner/native_presence/frame_codec.h"
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

#define BLOCK 131072u
#define BASE UINT64_C(9007199254741209)
#define MAX_INPUTS 48u
#define LEGACY "sdk-replay-opaque-legacy"

static double clock_ms(clockid_t clock)
{
    struct timespec t;
    if (clock_gettime(clock,&t)) return -1;
    return t.tv_sec*1000.0+t.tv_nsec/1e6;
}

static int until(double deadline)
{
    for (;;) {
        double left=deadline-clock_ms(CLOCK_MONOTONIC);
        if (left<=0) return 0;
        struct timespec delay={(time_t)(left/1000),(long)((left/1000-(time_t)(left/1000))*1e9)};
        if (nanosleep(&delay,NULL) && errno!=EINTR) return -1;
    }
}

static uint32_t u32(const unsigned char *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static uint64_t u64(const unsigned char *p)
{ return u32(p)|((uint64_t)u32(p+4)<<32); }

static int integer(const char *text,unsigned *value)
{
    char *end; errno=0;
    unsigned long n=strtoul(text,&end,10);
    if (!*text || *text=='-' || errno || *end || n>300000) return -1;
    *value=(unsigned)n; return 0;
}

static int emit(leo_scanner_glrt *sdk,int drain,uint64_t block,double origin,
    double *cost_cpu,double *cost_wall)
{
    unsigned char packet[1024];
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID),wall=clock_ms(CLOCK_MONOTONIC);
    ssize_t n=drain ? leo_scanner_glrt_drain(sdk,packet,sizeof(packet)) :
        leo_scanner_glrt_frame(sdk,LEGACY,sizeof(LEGACY)-1,packet,sizeof(packet));
    double ended=clock_ms(CLOCK_MONOTONIC);
    *cost_cpu+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    *cost_wall+=ended-wall;
    if (drain && n==-EAGAIN) return 0;
    if (n<=0) return -1;
    leo_glrt_frame_v1 decoded;
    if (leo_glrt_frame_decode(&decoded,packet,(size_t)n)) return -1;
    printf("{\"kind\":\"frame\",\"block\":%" PRIu64 ",\"elapsed_ms\":%.9f,\"hex\":\"",block,ended-origin);
    for (ssize_t i=0;i<n;++i) printf("%02x",packet[i]);
    puts("\"}");
    return decoded.flags&LEO_GLRT_FRAME_FINAL ? 2 : 1;
}

int main(int argc,char **argv)
{
    unsigned duration,delay,jitter,enabled;
    if (argc!=8 || integer(argv[4],&duration) || duration<242 ||
        integer(argv[5],&delay) || (delay!=0 && delay!=2) ||
        integer(argv[6],&jitter) || (jitter!=0 && jitter!=40) ||
        integer(argv[7],&enabled) || enabled>1) return 2;
    alarm(duration/1000+25);
    struct rlimit cpu={340,340},memory={192*1024*1024,192*1024*1024};
    if (setrlimit(RLIMIT_CPU,&cpu)) return 2;
#if !defined(__SANITIZE_ADDRESS__)
    if (setrlimit(RLIMIT_AS,&memory)) return 2;
#else
    (void)memory;
#endif
    FILE *input=fopen(argv[3],"rb");
    if (!input) return 2;
    unsigned char header[24];
    int status=2;
    int16_t *saved=NULL,*iq=NULL;
    leo_scanner_glrt *sdk=NULL;
    if (fread(header,1,12,input)!=12 || memcmp(header,"LDP1",4)) goto done;
    unsigned rate=u32(header+4),inputs=u32(header+8);
    if ((rate!=2500000 && rate!=5000000) || !inputs || inputs>MAX_INPUTS) goto done;
    size_t dwell=rate/50*6,guard=rate/1000,period=dwell+guard;
    unsigned jobs=duration/121;
    uint64_t source_counter[MAX_INPUTS],source_visit[MAX_INPUTS];
    unsigned edge[MAX_INPUTS],channel[MAX_INPUTS];
    saved=calloc((size_t)inputs*dwell,4); iq=calloc(BLOCK,8);
    if (!saved || !iq) goto done;
    for (unsigned j=0;j<inputs;++j) {
        if (fread(header,1,24,input)!=24) goto done;
        source_counter[j]=u64(header); source_visit[j]=u64(header+8);
        edge[j]=u32(header+16); channel[j]=u32(header+20);
        if (edge[j]>1 || channel[j]<1 || channel[j]>4 || source_counter[j]>UINT64_MAX-dwell ||
            fread(saved+(size_t)j*dwell*2,4,dwell,input)!=dwell) goto done;
    }
    if (fgetc(input)!=EOF || ferror(input)) goto done;
    fclose(input); input=NULL;
    leo_scanner_glrt_config_v1 config={.session=71,.generation=9,.rate_hz=rate,.rx=1,
        .maximum_visits=jobs,.maximum_block_samples=BLOCK};
    memset(config.algorithm_sha256,18,32); memset(config.configuration_sha256,52,32);
    double opened=clock_ms(CLOCK_MONOTONIC);
    if (enabled) {
        int ret=leo_scanner_glrt_open(&sdk,&config,argv[1],argv[2]);
        if (ret) { fprintf(stderr,"SDK startup rejected: %d\n",ret); goto done; }
    }
    double setup_ms=clock_ms(CLOCK_MONOTONIC)-opened;
    printf("{\"kind\":\"protocol\",\"schema\":\"leo-sdk-modeled-replay-v1\","
        "\"rate_hz\":%u,\"duration_ms\":%u,\"block_samples\":%u,\"jobs\":%u,\"inputs\":%u,"
        "\"delay_blocks\":%u,\"jitter_ms\":%u,\"enabled\":%u,\"base\":\"%" PRIu64 "\","
        "\"guard_samples\":%zu,\"setup_ms\":%.9f,\"synthetic_rx0_and_transition_padding\":true,"
        "\"original_arrivals\":false,\"live_rf\":false}\n",
        rate,duration,BLOCK,jobs,inputs,delay,jitter,enabled,BASE,guard,setup_ms);
    double origin=clock_ms(CLOCK_MONOTONIC);
    uint64_t total=(uint64_t)jobs*period,blocks=(total+BLOCK-1)/BLOCK;
    unsigned known=0;
    for (uint64_t block=0;block<blocks;++block) {
        uint64_t first=block*BLOCK;
        size_t count=total-first<BLOCK ? (size_t)(total-first) : BLOCK;
        double fill_start=clock_ms(CLOCK_MONOTONIC);
        size_t filled=0;
        while (filled<count) {
            uint64_t offset=first+filled,visit=offset/period;
            size_t within=(size_t)(offset%period),take=period-within;
            if (take>count-filled) take=count-filled;
            if (within<guard && take>guard-within) take=guard-within;
            const int16_t *src=within>=guard ? saved+(visit%inputs*dwell+within-guard)*2 : NULL;
            for (size_t j=0;j<take;++j) {
                int16_t *dest=iq+(filled+j)*4;
                dest[0]=30000; dest[1]=-30000;
                dest[2]=src ? src[j*2] : -29000;
                dest[3]=src ? src[j*2+1] : 29000;
            }
            filled+=take;
        }
        double fill_ms=clock_ms(CLOCK_MONOTONIC)-fill_start;
        double nominal_ms=(first+count)*1000.0/rate;
        double requested_ms=nominal_ms+(block%4==0 ? jitter : 0);
        if (until(origin+requested_ms)) goto done;
        double arrived=clock_ms(CLOCK_MONOTONIC)-origin;
        double callback_cpu=0,callback_wall=0;
        /* Model event observation after zero/two complete block deliveries.
         * The full stream contains sentinels in invalid intervals, never RF IQ. */
        while (known<jobs && ((uint64_t)known*period+guard)/BLOCK+delay<=block) {
            unsigned p=known%inputs;
            uint64_t start=BASE+(uint64_t)known*period+guard;
            double cpu_start=clock_ms(CLOCK_PROCESS_CPUTIME_ID),wall_start=clock_ms(CLOCK_MONOTONIC);
            if (enabled && leo_scanner_glrt_visit(sdk,known,start,start+dwell,channel[p],edge[p])) goto done;
            callback_cpu+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu_start;
            callback_wall+=clock_ms(CLOCK_MONOTONIC)-wall_start;
            printf("{\"kind\":\"visit\",\"visit\":%u,\"source_index\":%u,\"source_visit\":\"%" PRIu64
                "\",\"source_counter\":\"%" PRIu64 "\",\"start\":\"%" PRIu64 "\",\"end\":\"%" PRIu64
                "\",\"block\":%" PRIu64 "}\n",known,p,source_visit[p],source_counter[p],start,start+dwell,block);
            ++known;
        }
        double cpu_start=clock_ms(CLOCK_PROCESS_CPUTIME_ID),wall_start=clock_ms(CLOCK_MONOTONIC);
        if (enabled && leo_scanner_glrt_block(sdk,BASE+first,iq,count,4,2)) goto done;
        callback_cpu+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu_start;
        callback_wall+=clock_ms(CLOCK_MONOTONIC)-wall_start;
        if (enabled && emit(sdk,0,block,origin,&callback_cpu,&callback_wall)!=1) goto done;
        printf("{\"kind\":\"block\",\"block\":%" PRIu64 ",\"first\":\"%" PRIu64 "\",\"samples\":%zu,"
            "\"nominal_ms\":%.9f,\"requested_ms\":%.9f,\"arrival_ms\":%.9f,\"fill_ms\":%.9f,"
            "\"callback_cpu_ms\":%.9f,\"callback_wall_ms\":%.9f}\n",
            block,BASE+first,count,nominal_ms,requested_ms,arrived,fill_ms,callback_cpu,callback_wall);
        fflush(stdout);
    }
    if (known!=jobs) goto done;
    if (until(origin+duration)) goto done;
    if (enabled) {
        if (leo_scanner_glrt_finish(sdk,0)) goto done;
        int terminal=0;
        while (clock_ms(CLOCK_MONOTONIC)<origin+duration+5000) {
            double cpu_ms=0,wall_ms=0;
            int ret=emit(sdk,1,blocks,origin,&cpu_ms,&wall_ms);
            if (ret<0) goto done;
            if (ret==2) { terminal=1; break; }
            if (until(clock_ms(CLOCK_MONOTONIC)+1)) goto done;
        }
        if (!terminal) goto done;
    }
    printf("{\"kind\":\"summary\",\"jobs\":%u,\"blocks\":%" PRIu64 ",\"elapsed_ms\":%.9f}\n",
        jobs,blocks,clock_ms(CLOCK_MONOTONIC)-origin);
    status=0;
done:
    leo_scanner_glrt_close(sdk);
    if (input) fclose(input);
    free(saved); free(iq);
    return status;
}
