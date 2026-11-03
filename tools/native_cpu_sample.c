/* Bounded single-thread diagnostic sampler. Child stdout goes to the first argument;
 * stdout here contains user-mode instruction pointers, stderr lost samples.
 * No kernel configuration changes, RF access, or application modifications. */
#define _GNU_SOURCE
#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <errno.h>

static void copy_ring(void *out,const char *data,size_t capacity,uint64_t at,size_t n) {
    size_t offset=(size_t)(at%capacity),first=capacity-offset;
    if(first>n)first=n;
    memcpy(out,data+offset,first);memcpy((char*)out+first,data,n-first);
}
int main(int argc,char **argv) {
    if(argc<3){fprintf(stderr,"usage: cpu-sample CHILD_OUTPUT COMMAND [ARG...] (60s limit)\n");return 2;}
    int output=open(argv[1],O_WRONLY|O_CREAT|O_EXCL,0600);
    if(output<0){perror("output");return 2;}
    pid_t child=fork();if(child<0){close(output);return 2;}
    if(!child){dup2(output,STDOUT_FILENO);close(output);alarm(60);raise(SIGSTOP);execvp(argv[2],argv+2);_exit(127);}
    close(output);int status=0;
    if(waitpid(child,&status,WUNTRACED)!=child || !WIFSTOPPED(status))return 3;
    struct perf_event_attr attr;memset(&attr,0,sizeof(attr));attr.size=sizeof(attr);
    attr.type=PERF_TYPE_SOFTWARE;attr.config=PERF_COUNT_SW_CPU_CLOCK;
    attr.sample_type=PERF_SAMPLE_IP;attr.freq=1;attr.sample_freq=199;
    attr.disabled=1;attr.enable_on_exec=1;attr.inherit=0;
    attr.exclude_kernel=1;attr.exclude_hv=1;attr.wakeup_events=1;
    int fd=(int)syscall(__NR_perf_event_open,&attr,child,-1,-1,0);
    if(fd<0){perror("perf_event_open");kill(child,SIGKILL);waitpid(child,&status,0);return 3;}
    long page=sysconf(_SC_PAGESIZE);size_t capacity=(size_t)page*16,length=(size_t)page+capacity;
    void *mapping=mmap(NULL,length,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    if(mapping==MAP_FAILED){perror("mmap");kill(child,SIGKILL);waitpid(child,&status,0);close(fd);return 3;}
    struct perf_event_mmap_page *meta=mapping;const char *data=(const char*)mapping+page;
    kill(child,SIGCONT);uint64_t tail=0,lost=0,samples=0;int finished=0,error=0;
    while(!finished) {
        pid_t result=waitpid(child,&status,WNOHANG);
        if(result==child)finished=1;
        else if(result<0 && errno!=EINTR){error=1;break;}
        uint64_t head=meta->data_head;__sync_synchronize();
        if(head-tail>capacity){error=1;break;}
        while(tail<head) {
            struct perf_event_header header;copy_ring(&header,data,capacity,tail,sizeof(header));
            if(header.size<sizeof(header) || header.size>capacity || tail+header.size>head){error=1;break;}
            if(header.type==PERF_RECORD_SAMPLE && header.size>=16) {
                uint64_t ip;copy_ring(&ip,data,capacity,tail+sizeof(header),sizeof(ip));
                printf("%llx\n",(unsigned long long)ip);++samples;
            } else if(header.type==PERF_RECORD_LOST && header.size>=24) {
                uint64_t n;copy_ring(&n,data,capacity,tail+16,sizeof(n));lost+=n;
            }
            tail+=header.size;
        }
        __sync_synchronize();meta->data_tail=tail;
        if(error)break;
        if(!finished)usleep(10000);
    }
    if(!finished){kill(child,SIGKILL);waitpid(child,&status,0);}
    munmap(mapping,length);close(fd);
    int code=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
    fprintf(stderr,"samples=%llu lost=%llu child_exit=%d sampler_error=%d\n",
            (unsigned long long)samples,(unsigned long long)lost,code,error);
    return error?3:code;
}
