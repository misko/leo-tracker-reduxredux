/* Saved-IQ userspace replay only: no radio, IIO, or acquisition interface. */
#define _POSIX_C_SOURCE 200809L
#include "../src/leo/analysis/native_presence/window_rank.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <unistd.h>

static uint32_t u32(const unsigned char *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static uint64_t u64(const unsigned char *p)
{ return u32(p)|(uint64_t)u32(p+4)<<32; }

int main(int argc, char **argv)
{
    if (argc!=4) return 2;
    char *end=NULL;
    unsigned long bins=strtoul(argv[2],&end,10);
    if (!*argv[2] || *end || bins<512 || bins>8192 || (bins&(bins-1))) return 2;
    unsigned long repeats=strtoul(argv[3],&end,10);
    if (!*argv[3] || *end || repeats<1 || repeats>100) return 2;
    uint16_t endian=1;
    if (*(unsigned char *)&endian!=1 || sizeof(double)!=8) return 2;
    alarm(30);
    struct rlimit limit={64*1024*1024,64*1024*1024};
    if (setrlimit(RLIMIT_AS,&limit)) return 2;
    limit.rlim_cur=limit.rlim_max=25;
    if (setrlimit(RLIMIT_CPU,&limit)) return 2;
    FILE *input=fopen(argv[1],"rb");
    unsigned char header[28];
    if (!input) return 2;
    if (fread(header,1,sizeof(header),input)!=sizeof(header)) { fclose(input); return 2; }
    uint32_t rate=u32(header+4), edge=u32(header+8), count=u32(header+12);
    uint64_t counter=u64(header+20);
    if (memcmp(header,"LRK1",4) || (rate!=2500000 && rate!=5000000) || edge>1 ||
        count!=rate/50*6 || u32(header+16)!=2 || counter>UINT64_MAX-count) {
        fclose(input); return 2;
    }
    size_t n=(rate+375)/750;
    leo_presence_complex *exact=malloc(n*sizeof(*exact));
    int16_t *iq=malloc((size_t)count*4);
    leo_presence_rank_workspace *workspace=NULL;
    int status=2;
    if (!exact || !iq || fread(exact,sizeof(*exact),n,input)!=n ||
        fread(iq,4,count,input)!=count || fgetc(input)!=EOF || ferror(input)) goto done;
    workspace=leo_presence_rank_create(rate,exact,n,(uint32_t)bins);
    if (!workspace) goto done;
    for (unsigned long iteration=0; iteration<repeats; ++iteration) {
        leo_presence_rank_result result;
        if (leo_presence_rank_ci16(workspace,iq,count,&result)) goto done;
        printf("{\"rate_hz\":%u,\"edge\":%u,\"counter\":\"%" PRIu64
            "\",\"bins\":%lu,\"iteration\":%lu,\"scores\":[",
            rate,edge,counter,bins,iteration);
        for (int k=0;k<6;++k) printf("%s%.17g",k ? "," : "",result.scores[k]);
        printf("],\"order\":[");
        for (int k=0;k<6;++k) printf("%s%u",k ? "," : "",result.order[k]);
        printf("],\"projected_epoch_samples\":[");
        for (int k=0;k<6;++k) printf("%s%u",k ? "," : "",result.projected_epoch_samples[k]);
        printf("],\"fold_cpu_ms\":%.9g,\"correlation_cpu_ms\":%.9g,\"total_cpu_ms\":%.9g,\"total_wall_ms\":%.9g}\n",
            result.fold_cpu_ms,result.correlation_cpu_ms,result.total_cpu_ms,result.total_wall_ms);
    }
    if (fflush(stdout) || ferror(stdout)) goto done;
    status=0;
done:
    leo_presence_rank_destroy(workspace);
    free(exact); free(iq); fclose(input);
    return status;
}
