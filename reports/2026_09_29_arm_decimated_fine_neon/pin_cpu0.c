#define _GNU_SOURCE
#include <sched.h>
#include <unistd.h>
#include <stdio.h>
int main(int argc,char **argv) {
    if(argc<2)return 2;
    cpu_set_t allowed;CPU_ZERO(&allowed);CPU_SET(0,&allowed);
    if(sched_setaffinity(0,sizeof(allowed),&allowed)){perror("sched_setaffinity");return 3;}
    execv(argv[1],argv+1);perror("execv");return 4;
}
