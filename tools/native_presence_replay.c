/* Bounded saved-IQ replay only: no IIO, sockets, device nodes, or radio control. */
#define _POSIX_C_SOURCE 200809L
#include "../src/leo/analysis/native_presence/presence.h"
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

static int read_u32(FILE *f, uint32_t *out)
{
    unsigned char b[4];
    if (fread(b,1,4,f)!=4) return -1;
    *out=(uint32_t)b[0]|(uint32_t)b[1]<<8|(uint32_t)b[2]<<16|(uint32_t)b[3]<<24;
    return 0;
}

int main(int argc, char **argv)
{
    if (argc!=3) { fprintf(stderr,"usage: native-presence-replay PROBE ITERATIONS\n"); return 2; }
    char *end; errno=0; long repeats=strtol(argv[2],&end,10);
    if (errno || *end || repeats<1 || repeats>20) return 2;
    struct rlimit cpu={60,60}, memory={128*1024*1024,128*1024*1024};
    if (setrlimit(RLIMIT_CPU,&cpu)) return 2;
#if !defined(__SANITIZE_ADDRESS__)
    if (setrlimit(RLIMIT_AS,&memory)) return 2;
#else
    /* ASan reserves a huge virtual shadow; the normal replay remains capped. */
    (void)memory;
#endif
    alarm(90);
    uint16_t endian=1;
    if (*(unsigned char *)&endian!=1 || sizeof(double)!=8 || sizeof(leo_presence_complex)!=16)
        return 2;
    FILE *input=fopen(argv[1],"rb");
    if (!input) { perror("probe"); return 2; }
    char magic[4]; uint32_t rate,edge,count,format,lo,hi;
    if (fread(magic,1,4,input)!=4 || memcmp(magic,"LPR1",4) ||
        read_u32(input,&rate) || read_u32(input,&edge) || read_u32(input,&count) ||
        read_u32(input,&format) || read_u32(input,&lo) || read_u32(input,&hi) ||
        (rate!=2500000 && rate!=5000000) || edge>1 || (format!=1 && format!=2) ||
        count!=(rate/50)) { fclose(input); return 2; }
    size_t n=(size_t)nearbyint(rate/750.0);
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    size_t sample_bytes=format==1 ? 16 : 4;
    void *samples=calloc(count,sample_bytes);
    int status=2;
    leo_presence_workspace *workspace=NULL;
    if (!exact || !control || !samples) goto done;
    if (fread(exact,sizeof(*exact),n,input)!=n || fread(control,sizeof(*control),n,input)!=n ||
        fread(samples,sample_bytes,count,input)!=count || fgetc(input)!=EOF || ferror(input)) goto done;
    workspace=leo_presence_create(rate,exact,control,n);
    if (!workspace) goto done;
    for (int repeat=0; repeat<repeats; ++repeat) {
        leo_presence_result result;
        int rc=format==1 ? leo_presence_run(workspace,samples,count,&result) :
            leo_presence_run_ci16(workspace,samples,count,&result);
        if (rc) goto done;
        printf("{\"schema\":\"native-presence-replay-v1\",\"rate_hz\":%u,\"edge\":%u,"
            "\"device_counter\":\"%" PRIu64 "\",\"iteration\":%d,\"format\":%u,"
            "\"conversion_cpu_ms\":%.9g,\"coarse_cpu_ms\":%.9g,\"fine_cpu_ms\":%.9g,"
            "\"fractional_cpu_ms\":%.9g,\"total_cpu_ms\":%.9g,\"total_wall_ms\":%.9g,"
            "\"candidates\":[",rate,edge,((uint64_t)hi<<32)|lo,repeat,format,
            result.conversion_cpu_ms,result.coarse_cpu_ms,result.fine_cpu_ms,
            result.fractional_cpu_ms,result.total_cpu_ms,result.total_wall_ms);
        for (int k=0;k<result.candidate_count;++k) {
            leo_presence_candidate *c=&result.candidates[k];
            printf("%s{\"epoch\":%d,\"fractional_complete\":%d,\"acquired_cfo_hz\":%.17g,"
                "\"fractional_offset_samples\":%.17g,\"tracking_cfo_hz\":%.17g,"
                "\"exact_score\":%.17g,\"control_score\":%.17g,\"margin\":%.17g}",
                k ? ",":"",c->epoch,c->fractional_complete,c->acquired_cfo_hz,
                c->fractional_offset_samples,c->tracking_cfo_hz,c->exact_score,c->control_score,c->margin);
        }
        struct rusage usage;
        if (getrusage(RUSAGE_SELF,&usage)) goto done;
        printf("],\"max_rss_kib\":%ld}\n",usage.ru_maxrss);
        fflush(stdout);
    }
    status=0;
done:
    leo_presence_destroy(workspace);
    free(exact); free(control); free(samples); fclose(input);
    return status;
}
