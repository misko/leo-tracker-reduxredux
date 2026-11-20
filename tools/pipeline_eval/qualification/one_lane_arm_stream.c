/* Saved dual CI16 replay for sequential stock and two real one-RX paths. */
#define _GNU_SOURCE
#define LEO_NATIVE_GLRT_SHORT_WINDOW_CLI 1
#define main leo_prior_ordinary_main
#include "native_glrt_cli.c"
#undef main
#include "single_rx_glrt.h"
#include "short_window_glrt.h"
#include <inttypes.h>

int leo_one_lane_strided_short_v1(leo_single_rx_glrt *, const int16_t *, size_t, int,
    leo_native_glrt_result *);

typedef struct { uint64_t cpu, wall; } clocks;

static void require(int good, const char *message)
{
    if (!good) { fprintf(stderr,"%s\n",message); exit(2); }
}

static uint64_t nanos(clockid_t id)
{
    struct timespec now;
    require(clock_gettime(id,&now)==0,"clock_gettime");
    return (uint64_t)now.tv_sec*UINT64_C(1000000000)+(uint64_t)now.tv_nsec;
}

static clocks sample_clocks(void)
{
    return (clocks){nanos(CLOCK_THREAD_CPUTIME_ID),nanos(CLOCK_MONOTONIC)};
}

static void timing(const char *name, clocks a, clocks b)
{
    printf(",\"%s\":[%" PRIu64 ",%" PRIu64 "]",name,b.cpu-a.cpu,b.wall-a.wall);
}

static void read_saved_visit(const char *file, void *out, size_t element, size_t count)
{
    FILE *f=fopen(file,"rb");
    require(f!=NULL,"opening saved bytes");
    const int good=fread(out,element,count,f)==count && fgetc(f)==EOF && !ferror(f);
    require(fclose(f)==0 && good,"reading exact saved bytes");
}

int main(int argc, char **argv)
{
    enum { times=200000, frame=13333, rate=10000000 };
    const uint16_t little=1;
    require(*(const uint8_t *)&little==1 && argc>=6 && (argc-4)%2==0,
        "usage: one-lane-arm dual|packed|strided exact.c16 control.c16 lane iq.ci16 ...");
    const int dual=!strcmp(argv[1],"dual"), packed=!strcmp(argv[1],"packed");
    require(dual || packed || !strcmp(argv[1],"strided"),"unknown replay mode");
    leo_native_glrt_complex *exact=malloc(frame*sizeof(*exact)), *control=malloc(frame*sizeof(*control));
    int16_t *iq=malloc(4u*times*sizeof(*iq)), *copy=packed ? malloc(2u*times*sizeof(*copy)) : NULL;
    require(exact && control && iq && (!packed || copy),"allocating fixture storage");
    read_saved_visit(argv[2],exact,sizeof(*exact),frame);
    read_saved_visit(argv[3],control,sizeof(*control),frame);
    leo_native_glrt *both=NULL;
    leo_single_rx_glrt *single=NULL;
    const uint32_t fractional=LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH;
    const clocks starting=sample_clocks();
    const int created=dual
        ? leo_native_glrt_create_with_mode(&both,rate,exact,control,frame,fractional)
        : leo_single_rx_glrt_create_with_mode(&single,rate,exact,control,frame,fractional);
    const clocks ready=sample_clocks();
    require(!created,"native detector initialization failed");
    printf("{\"kind\":\"setup\",\"one_rx\":%s",dual ? "false" : "true");
    timing("setup",starting,ready);
    puts("}");
    for (int repeat=0;repeat<2;++repeat) for (int i=4;i<argc;i+=2) {
        const int lane=argv[i][0]-'0';
        require(strlen(argv[i])==1 && (lane==0 || lane==1),"expected a physical lane");
        const clocks start=sample_clocks();
        read_saved_visit(argv[i+1],iq,sizeof(*iq),4u*times);
        const clocks buffered=sample_clocks();
        if (packed) for (size_t k=0;k<times;++k) {
            copy[2*k]=iq[4*k+2*lane];
            copy[2*k+1]=iq[4*k+2*lane+1];
        }
        const clocks staged=sample_clocks();
        leo_native_glrt_result result;
        const int status=dual ? leo_native_glrt_analyze_short_window(both,iq,times,&result)
            : packed ? leo_single_rx_glrt_analyze_short_window(single,copy,times,&result)
            : leo_one_lane_strided_short_v1(single,iq,times,lane,&result);
        const clocks measured=sample_clocks();
        require(!status && result.row_count==(dual ? 2u : 1u),"native physical-lane search failed");
        require(result.rows[0].receiver_id==0,"unexpected native first receiver");
        if (!dual) {
            const leo_native_glrt_row blank = {.receiver_id=1-lane,
                .probe_index=result.rows[0].probe_index,.probe_start_ms=result.rows[0].probe_start_ms};
            result.rows[0].receiver_id=lane;
            if (lane==1) result.rows[1]=result.rows[0];
            result.rows[1-lane]=blank;
        }
        const clocks remapped=sample_clocks();
        printf("{\"kind\":\"visit\",\"index\":%d,\"repeat\":%d,\"selected\":%d,"
            "\"native_rows\":%zu,\"input_bytes\":%zu,\"staged_bytes\":%zu",
            (i-4)/2,repeat,lane,result.row_count,sizeof(*iq)*4u*times,
            packed ? sizeof(*copy)*2u*times : 0u);
        timing("read",start,buffered);
        timing("stage",buffered,staged);
        timing("native",staged,measured);
        timing("map",measured,remapped);
        timing("total",buffered,remapped);
        fputs(",\"rows\":[",stdout);
        row(&result.rows[0]); putchar(','); row(&result.rows[1]); puts("]}");
    }
    require(dual ? !leo_native_glrt_destroy(both) : !leo_single_rx_glrt_destroy(single),"closing detector");
    free(copy); free(iq); free(control); free(exact);
    return EXIT_SUCCESS;
}
