/* Minimal on-device execution deadline; no shell, capture, or privileged action. */
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
int main(int argc,char **argv) {
    if(argc<3) {fprintf(stderr,"usage: run-bounded SECONDS EXECUTABLE [ARG...]\n");return 2;}
    char *end;errno=0;unsigned long seconds=strtoul(argv[1],&end,10);
    if(errno || *end || seconds<1 || seconds>600) return 2;
    if(signal(SIGALRM,SIG_DFL)==SIG_ERR) return 2;
    alarm((unsigned)seconds);
    execvp(argv[2],argv+2);perror("exec");return 127;
}
