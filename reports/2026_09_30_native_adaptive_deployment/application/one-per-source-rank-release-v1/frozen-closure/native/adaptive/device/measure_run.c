/* Whole-process timing includes loading/setup/output; no detector-only claim. */
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
static double seconds(struct timespec t) {return t.tv_sec+t.tv_nsec*1e-9;}
int main(int argc,char **argv) {
    if(argc<3) return 2;
    char *end;errno=0;unsigned long limit=strtoul(argv[1],&end,10);
    if(errno || end==argv[1] || *end || limit<1 || limit>600) return 2;
    struct timespec begin,finish;struct rusage usage={0};int status;
    if(clock_gettime(CLOCK_MONOTONIC,&begin)) return 2;
    pid_t child=fork();if(child<0) return 2;
    if(!child) {signal(SIGALRM,SIG_DFL);alarm((unsigned)limit);execvp(argv[2],argv+2);_exit(127);}
    while(wait4(child,&status,0,&usage)<0) if(errno!=EINTR) return 2;
    if(clock_gettime(CLOCK_MONOTONIC,&finish)) return 2;
    int code=WIFEXITED(status) ? WEXITSTATUS(status) : 128+WTERMSIG(status);
    double cpu=usage.ru_utime.tv_sec+usage.ru_stime.tv_sec+
        (usage.ru_utime.tv_usec+usage.ru_stime.tv_usec)*1e-6;
    fprintf(stderr,"{\"scope\":\"whole_process\",\"wall_s\":%.9f,\"cpu_s\":%.9f,"
        "\"max_rss_kib\":%ld,\"exit_code\":%d}\n",seconds(finish)-seconds(begin),cpu,usage.ru_maxrss,code);
    return code;
}
