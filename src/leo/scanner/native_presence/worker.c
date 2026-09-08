/* Isolated Linux userspace consumer. Acquisition owns all hardware and copies
 * probes into the shared pool. This executable only inherits that mapping,
 * a notification pipe, and immutable templates; never an IIO buffer or handle. */
#define _GNU_SOURCE
#include "pool.h"
#include "../../analysis/native_presence/dwell.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <limits.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>

static int descriptor(const char *value)
{
    char *end; errno=0; long fd=strtol(value,&end,10);
    return errno || !*value || *end || fd<3 || fd>INT_MAX ? -1 : (int)fd;
}

static int close_unrelated(int mapping, int notify, int templates)
{
    DIR *directory=opendir("/proc/self/fd");
    if (!directory) return -1;
    struct dirent *entry;
    while ((entry=readdir(directory))) {
        int fd=descriptor(entry->d_name);
        if (fd>=3 && fd!=mapping && fd!=notify && fd!=templates && fd!=dirfd(directory)) close(fd);
    }
    closedir(directory); close(STDIN_FILENO);
    return 0;
}

static int read_exact(int fd, void *buffer, size_t count)
{
    unsigned char *out=buffer;
    while (count) {
        ssize_t n=read(fd,out,count);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) return -1;
        out+=n; count-=(size_t)n;
    }
    return 0;
}

static uint32_t u32(const unsigned char *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }

int main(int argc, char **argv)
{
    if (argc!=5) { fprintf(stderr,"usage: presence-worker POOL_FD NOTIFY_FD TEMPLATE_FD PARENT_PID\n"); return 2; }
    int mapping=descriptor(argv[1]), notify=descriptor(argv[2]), templates=descriptor(argv[3]);
    int parent=descriptor(argv[4]);
    if (mapping<0 || notify<0 || templates<0 || parent<0 ||
        mapping==notify || mapping==templates || notify==templates || getppid()!=parent) return 2;
    sigset_t empty; sigemptyset(&empty);
    struct sigaction action={.sa_handler=SIG_DFL}; sigemptyset(&action.sa_mask);
    if (sigprocmask(SIG_SETMASK,&empty,NULL) || sigaction(SIGTERM,&action,NULL) ||
        prctl(PR_SET_PDEATHSIG,SIGTERM) || getppid()!=parent || close_unrelated(mapping,notify,templates)) return 2;
    struct rlimit cpu={340,340}, memory={128*1024*1024,128*1024*1024};
    if (setrlimit(RLIMIT_CPU,&cpu)) return 2;
#if !defined(__SANITIZE_ADDRESS__)
    if (setrlimit(RLIMIT_AS,&memory)) return 2;
#else
    (void)memory;
#endif
    alarm(370);
    /* In the ARM root-launched case, retain only access to already-open IPC.
     * No account creation, capabilities, root filesystem writes, or RF access. */
    if (geteuid()==0 && (setgroups(0,NULL) || setgid(65534) || setuid(65534))) return 2;
    if (prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)) return 2;
    /* Changing credentials clears PDEATHSIG on Linux; install it again. */
    if (prctl(PR_SET_PDEATHSIG,SIGTERM) || getppid()!=parent) return 2;
    struct stat meta;
    if (fstat(notify,&meta) || !S_ISFIFO(meta.st_mode)) return 2;
    if (fstat(mapping,&meta) || !S_ISREG(meta.st_mode) ||
        (meta.st_size!=(off_t)leo_probe_pool_bytes() && meta.st_size!=(off_t)leo_dwell_pool_bytes())) return 2;
    size_t pool_bytes=(size_t)meta.st_size;
    leo_probe_pool *pool=mmap(NULL,pool_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,mapping,0);
    if (pool==MAP_FAILED) return 2;
    close(mapping);
    uint64_t session,generation; uint32_t rate,dwell,rx;
    int status=2;
    leo_presence_workspace *workspaces[2]={NULL,NULL};
    leo_presence_dwell_workspace *dwells[2]={NULL,NULL};
    leo_presence_complex *exact=NULL,*control=NULL;
    if (leo_probe_pool_configuration(pool,&session,&generation,&rate) ||
        leo_probe_pool_geometry(pool,&dwell,&rx) ||
        pool_bytes!=(dwell ? leo_dwell_pool_bytes() : leo_probe_pool_bytes())) goto done;
    unsigned char header[12];
    uint16_t endian=1;
    if (*(unsigned char *)&endian!=1 || sizeof(double)!=8 ||
        fstat(templates,&meta) || !S_ISREG(meta.st_mode) || lseek(templates,0,SEEK_SET)!=0 ||
        read_exact(templates,header,sizeof(header))) goto done;
    size_t n=(size_t)nearbyint(rate/750.0);
    int mode=fcntl(templates,F_GETFL);
    int immutable=mode>=0 && (mode&O_ACCMODE)==O_RDONLY;
    if (header[0]!='L' || header[1]!='P' || header[2]!='T' || header[3]!='1' ||
        !immutable || u32(header+4)!=rate || u32(header+8)!=n ||
        meta.st_size!=(off_t)(12+4*n*sizeof(*exact))) goto done;
    exact=calloc(n,sizeof(*exact)); control=calloc(n,sizeof(*control));
    if (!exact || !control) goto done;
    for (int edge=0; edge<2; ++edge) {
        if (read_exact(templates,exact,n*sizeof(*exact)) || read_exact(templates,control,n*sizeof(*control))) goto done;
        if (dwell) {
            dwells[edge]=leo_presence_dwell_create(rate,exact,control,n,512);
            if (!dwells[edge]) goto done;
        } else {
            workspaces[edge]=leo_presence_create(rate,exact,control,n);
            if (!workspaces[edge]) goto done;
        }
    }
    close(templates); templates=-1;
    if (write(STDOUT_FILENO,"ready\n",6)!=6) goto done;
    int eof=0;
    for (;;) {
        uint32_t slot; const int16_t *samples;
        leo_probe_result result={0};
        int taken=leo_probe_take(pool,&slot,&result.request,&samples);
        if (taken<0) goto done;
        if (taken) {
            if (result.request.session!=session || result.request.generation!=generation ||
                result.request.rate_hz!=rate || result.request.sample_count!=rate/50*(dwell ? 6u : 1u) ||
                result.request.edge>1 || (dwell && result.request.rx!=rx)) goto done;
            if (dwell) {
                leo_presence_dwell_workspace *w=dwells[result.request.edge];
                leo_presence_dwell_result out;
                result.status=leo_presence_dwell_run_ci16(w,samples,result.request.sample_count,1,0,&out);
                if (!result.status) {
                    if (leo_presence_dwell_get_screens(w,&result.dwell.screens)) goto done;
                    result.evidence=out.confirmations[0]; result.nuisance=out.nuisances[0];
                    result.dwell.rank=out.rank;
                    result.dwell.search_window_mask=63;
                    result.dwell.confirmation_window_mask=out.confirmation_window_mask;
                    result.dwell.total_cpu_ms=out.total_cpu_ms;
                    result.dwell.total_wall_ms=out.total_wall_ms;
                }
            } else {
                leo_presence_workspace *w=workspaces[result.request.edge];
                result.status=leo_presence_run_ci16(w,samples,result.request.sample_count,&result.evidence);
                if (leo_presence_get_nuisance(w,&result.nuisance)) goto done;
            }
            if (leo_probe_complete(pool,slot,&result)) goto done;
            continue;
        }
        if (eof) {
            leo_probe_stats stats; leo_probe_pool_stats(pool,&stats);
            status=stats.occupied_slots ? 2 : 0;
            break;
        }
        struct pollfd event={.fd=notify,.events=POLLIN};
        int rc=poll(&event,1,500);
        if (rc<0 && errno==EINTR) continue;
        if (rc<0 || (event.revents&(POLLERR|POLLNVAL))) goto done;
        if (rc>0) {
            unsigned char bytes[128];
            ssize_t received=read(notify,bytes,sizeof(bytes));
            if (received==0) eof=1;
            else if (received<0 && errno!=EAGAIN && errno!=EINTR) goto done;
        }
    }
done:
    for (int edge=0; edge<2; ++edge) {
        leo_presence_destroy(workspaces[edge]);
        leo_presence_dwell_destroy(dwells[edge]);
    }
    free(exact); free(control);
    if (templates>=0) close(templates);
    close(notify); munmap(pool,pool_bytes);
    return status;
}
