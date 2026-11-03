#include "adi-rx-counter.h"
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static int mode,closed;
int pluto_caps_main(int,char**);
int __wrap_open(const char *path,int flags,...) {
    (void)flags;assert(!strcmp(path,"/dev/tandem-agc-events"));
    if(mode==1) {errno=ENOENT;return -1;} return 42;
}
int __wrap_close(int fd) {assert(fd==42);++closed;return 0;}
int __wrap_ioctl(int fd,unsigned long request,...) {
    assert(fd==42);assert(request==ADI_RX_COUNTER_IOC_GET_SCAN_CAPS);
    if(mode==2) {errno=ENOTTY;return -1;}
    va_list args;va_start(args,request);
    struct adi_rx_counter_scan_caps *c=va_arg(args,struct adi_rx_counter_scan_caps*);
    va_end(args);memset(c,0,sizeof(*c));
    c->magic=ADI_RX_COUNTER_MAGIC;c->version=ADI_RX_COUNTER_SCAN_VERSION;
    c->size=sizeof(*c);c->features=ADI_RX_COUNTER_SCAN_FEATURES;
    c->maximum_profiles=8;c->source_counter_bits=32;c->frequency_resolution_hz=2;
    if(mode==3)c->version=99;
    if(mode==4)c->features=0;
    if(mode==5)c->reserved[0]=1;
    if(mode==6)c->source_counter_bits=64;
    return 0;
}
int main(void) {
    char *args[]={"pluto-local-caps",NULL};
    for(mode=0;mode<7;++mode) {
        closed=0;int rc=pluto_caps_main(1,args);
        assert(rc==(mode==0 ? 0 : mode<=2 ? 2 : 3));
        assert(closed==(mode==1 ? 0 : 1));
    }
    puts("{\"status\":\"pass\",\"capability_cases\":7,\"hardware_access\":false}");
}
