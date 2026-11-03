/* Read-only capability probe: never acquires capture, retunes, or enables RF. */
#include "adi-rx-counter.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(int argc,char **argv) {
    if(argc>2) {fprintf(stderr,"usage: pluto-local-caps [counter-device]\n");return 2;}
    const char *path=argc==2 ? argv[1] : "/dev/tandem-agc-events";
    int fd=open(path,O_RDONLY|O_CLOEXEC);
    if(fd<0) {fprintf(stderr,"open counter device: %s\n",strerror(errno));return 2;}
    struct adi_rx_counter_scan_caps caps={0};
    int rc=ioctl(fd,ADI_RX_COUNTER_IOC_GET_SCAN_CAPS,&caps);
    int saved=errno; close(fd);
    if(rc<0) {fprintf(stderr,"read scan capabilities: %s\n",strerror(saved));return 2;}
    if(caps.magic!=ADI_RX_COUNTER_MAGIC || caps.version!=ADI_RX_COUNTER_SCAN_VERSION ||
       caps.size!=sizeof(caps) || caps.features!=ADI_RX_COUNTER_SCAN_FEATURES ||
       caps.maximum_profiles!=ADI_RX_COUNTER_SCAN_MAX_PROFILES || caps.source_counter_bits!=32 ||
       caps.frequency_resolution_hz!=2 || caps.reserved[0] || caps.reserved[1]) {
        fprintf(stderr,"unsupported scan kernel ABI\n");return 3;
    }
    printf("{\"status\":\"compatible\",\"scan_abi\":%u,\"features\":%u,"
           "\"profiles\":%u,\"counter_bits\":%u,\"frequency_resolution_hz\":%u,"
           "\"acquisition_started\":false,\"transport\":\"local_ioctl\"}\n",
           caps.version,caps.features,caps.maximum_profiles,caps.source_counter_bits,
           caps.frequency_resolution_hz);
    return 0;
}
