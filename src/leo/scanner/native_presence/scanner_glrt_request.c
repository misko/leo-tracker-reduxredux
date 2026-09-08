#include "scanner_glrt.h"
#include "frame_codec.h"
#include <errno.h>
#include <string.h>

static uint32_t get32(const uint8_t *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static uint64_t get64(const uint8_t *p)
{ return (uint64_t)get32(p)|(uint64_t)get32(p+4)<<32; }
static void put32(uint8_t *p,uint32_t v)
{ for(unsigned j=0;j<4;++j) p[j]=(uint8_t)(v>>(j*8)); }
static void put64(uint8_t *p,uint64_t v)
{ put32(p,(uint32_t)v); put32(p+4,(uint32_t)(v>>32)); }
static int valid(const leo_scanner_glrt_request_v1 *r)
{
    if (!r || !r->generation || r->rx!=1 || !r->legacy_request || !r->legacy_bytes ||
        r->legacy_bytes>LEO_SCANNER_GLRT_REQUEST_MAX_BYTES-LEO_SCANNER_GLRT_REQUEST_HEADER_BYTES) return 0;
    uint8_t a=0,c=0;
    for(unsigned j=0;j<32;++j) { a|=r->algorithm_sha256[j]; c|=r->configuration_sha256[j]; }
    return a && c;
}
int leo_scanner_glrt_request_decode(leo_scanner_glrt_request_v1 *out,const void *packet,size_t bytes)
{
    if (!out || !packet || bytes<=LEO_SCANNER_GLRT_REQUEST_HEADER_BYTES || bytes>LEO_SCANNER_GLRT_REQUEST_MAX_BYTES) return -EINVAL;
    const uint8_t *p=packet;
    if (memcmp(p,"LGO1",4) || p[4]!=1 || p[5] || p[6]!=96 || p[7] || get32(p+8)!=bytes ||
        get32(p+12)!=bytes-96 || get32(p+28)) return -EINVAL;
    leo_scanner_glrt_request_v1 r={.generation=get64(p+16),.rx=get32(p+24),
        .legacy_request=p+96,.legacy_bytes=bytes-96};
    memcpy(r.algorithm_sha256,p+32,32); memcpy(r.configuration_sha256,p+64,32);
    if (!valid(&r)) return -EINVAL;
    *out=r; return 0;
}
ssize_t leo_scanner_glrt_request_encode(const leo_scanner_glrt_request_v1 *r,void *packet,size_t capacity)
{
    if (!packet || !valid(r)) return -EINVAL;
    size_t bytes=96+r->legacy_bytes;
    if (capacity<bytes) return -ENOSPC;
    uint8_t *p=packet;
    memcpy(p,"LGO1",4); p[4]=1; p[5]=0; p[6]=96; p[7]=0;
    put32(p+8,(uint32_t)bytes); put32(p+12,(uint32_t)r->legacy_bytes);
    put64(p+16,r->generation); put32(p+24,r->rx); put32(p+28,0);
    memcpy(p+32,r->algorithm_sha256,32); memcpy(p+64,r->configuration_sha256,32);
    memcpy(p+96,r->legacy_request,r->legacy_bytes);
    return (ssize_t)bytes;
}

int leo_scanner_glrt_legacy_view(const void *packet,size_t bytes,
    const uint8_t **legacy,size_t *legacy_bytes)
{ return leo_glrt_frame_legacy_view(packet,bytes,legacy,legacy_bytes) ? -EINVAL : 0; }
