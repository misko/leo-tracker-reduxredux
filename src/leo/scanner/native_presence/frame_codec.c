#include "frame_codec.h"
#include <float.h>
#include <math.h>
#include <string.h>

_Static_assert(sizeof(double)==8 && DBL_MANT_DIG==53 && DBL_MAX_EXP==1024,
    "GLRT metadata requires IEEE-754 binary64");

static uint16_t get16(const uint8_t *p)
{ return (uint16_t)p[0]|(uint16_t)p[1]<<8; }
static uint32_t get32(const uint8_t *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static uint64_t get64(const uint8_t *p)
{ return (uint64_t)get32(p)|((uint64_t)get32(p+4)<<32); }
static double get_double(const uint8_t *p)
{ uint64_t bits=get64(p); double value; memcpy(&value,&bits,8); return value; }
static void put16(uint8_t *p, uint16_t value)
{ p[0]=(uint8_t)value; p[1]=(uint8_t)(value>>8); }
static void put32(uint8_t *p, uint32_t value)
{ for (int j=0;j<4;++j) p[j]=(uint8_t)(value>>(j*8)); }
static void put64(uint8_t *p, uint64_t value)
{ put32(p,(uint32_t)value); put32(p+4,(uint32_t)(value>>32)); }
static void put_double(uint8_t *p, double value)
{ uint64_t bits; memcpy(&bits,&value,8); put64(p,bits); }

static int valid_record(const leo_glrt_classification_v1 *r)
{
    if (!r->rate_hz || r->channel<1 || r->channel>4 || r->edge>1 || r->rx>1 ||
        r->verdict>LEO_GLRT_NO_SIGNAL || r->reason>LEO_GLRT_CANCELLED || r->search_window_mask>63 ||
        r->valid_end<=r->valid_start || r->valid_end-r->valid_start!=(uint64_t)r->rate_hz*120/1000 ||
        r->search_start<r->valid_start || r->search_end<r->search_start || r->search_end>r->valid_end ||
        r->confirmation_start<r->search_start || r->confirmation_end<r->confirmation_start ||
        r->confirmation_end>r->search_end ||
        ((r->verdict==LEO_GLRT_UNAVAILABLE)!=(r->reason!=LEO_GLRT_COMPLETE))) return 0;
    uint64_t span=r->valid_end-r->valid_start;
    /* span <= UINT32_MAX * 120 / 1000, so these products cannot overflow. */
    for (unsigned bit=0;bit<6;++bit) if (r->search_window_mask&(1u<<bit)) {
        if (r->search_start>r->valid_start+span*bit/6 ||
            r->search_end<r->valid_start+span*(bit+1)/6) return 0;
    }
    if (r->verdict==LEO_GLRT_NO_SIGNAL && r->search_window_mask!=63) return 0;
    if (!isfinite(r->exact_score) || !isfinite(r->control_score) || !isfinite(r->margin) ||
        !isfinite(r->cfo_hz) || !isfinite(r->fractional_offset_samples) ||
        !isfinite(r->cpu_ms) || !isfinite(r->wall_ms) || r->exact_score<0 || r->control_score<0 ||
        fabs(r->fractional_offset_samples)>2 || r->cpu_ms<0 || r->wall_ms<0) return 0;
    double difference=r->exact_score-r->control_score;
    if (fabs(r->margin-difference)>fmax(1e-12,1e-12*fmax(fabs(r->margin),fabs(difference)))) return 0;
    if (r->verdict==LEO_GLRT_STARLINK && (!r->search_window_mask ||
        r->confirmation_end==r->confirmation_start || r->margin<=0)) return 0;
    if (r->confirmation_end>r->confirmation_start) {
        if (r->epoch_sample_counter<r->confirmation_start || r->epoch_sample_counter>=r->confirmation_end) return 0;
    } else if (r->exact_score || r->control_score || r->margin || r->cfo_hz ||
        r->epoch_sample_counter || r->fractional_offset_samples) return 0;
    return 1;
}

static int valid_frame(const leo_glrt_frame_v1 *f)
{
    if (!f || !f->session || !f->generation || f->flags>7 ||
        f->result_count>LEO_GLRT_FRAME_MAX_RECORDS ||
        f->legacy_bytes>LEO_GLRT_FRAME_MAX_BYTES-LEO_GLRT_FRAME_HEADER_BYTES ||
        LEO_GLRT_FRAME_HEADER_BYTES+f->legacy_bytes+f->result_count*LEO_GLRT_RECORD_BYTES>LEO_GLRT_FRAME_MAX_BYTES ||
        (f->legacy_bytes && !f->legacy_metadata) ||
        (!!(f->flags&LEO_GLRT_FRAME_DRAIN)!=(f->legacy_bytes==0)) ||
        ((f->flags&LEO_GLRT_FRAME_FINAL) && !(f->flags&LEO_GLRT_FRAME_DRAIN)) ||
        f->dropped_results>f->result_sequence_limit) return 0;
    uint8_t algorithm=0,configuration=0;
    for (int j=0;j<32;++j) { algorithm|=f->algorithm_sha256[j]; configuration|=f->configuration_sha256[j]; }
    if (!algorithm || !configuration) return 0;
    for (unsigned j=0;j<f->result_count;++j) {
        const leo_glrt_classification_v1 *r=&f->results[j];
        if (!valid_record(r) || r->sequence>=f->result_sequence_limit ||
            (j && r->sequence<=f->results[j-1].sequence)) return 0;
    }
    return 1;
}

int leo_glrt_frame_encode(const leo_glrt_frame_v1 *f, void *output, size_t capacity, size_t *written)
{
    if (!output || !written || !valid_frame(f)) return -1;
    size_t total=LEO_GLRT_FRAME_HEADER_BYTES+f->legacy_bytes+f->result_count*LEO_GLRT_RECORD_BYTES;
    if (capacity<total) return -1;
    uint8_t *p=output;
    memcpy(p,"LGC1",4); put16(p+4,1); put16(p+6,LEO_GLRT_FRAME_HEADER_BYTES);
    put32(p+8,(uint32_t)total); put32(p+12,f->legacy_bytes);
    put16(p+16,(uint16_t)f->result_count); put16(p+18,LEO_GLRT_RECORD_BYTES); put32(p+20,f->flags);
    put64(p+24,f->session); put64(p+32,f->generation); put64(p+40,f->frame_sequence);
    put64(p+48,f->result_sequence_limit); put64(p+56,f->dropped_results);
    memcpy(p+64,f->algorithm_sha256,32); memcpy(p+96,f->configuration_sha256,32);
    if (f->legacy_bytes) memcpy(p+LEO_GLRT_FRAME_HEADER_BYTES,f->legacy_metadata,f->legacy_bytes);
    p+=LEO_GLRT_FRAME_HEADER_BYTES+f->legacy_bytes;
    for (unsigned j=0;j<f->result_count;++j,p+=LEO_GLRT_RECORD_BYTES) {
        const leo_glrt_classification_v1 *r=&f->results[j];
        put64(p,r->sequence); put64(p+8,r->visit); put64(p+16,r->valid_start); put64(p+24,r->valid_end);
        put64(p+32,r->search_start); put64(p+40,r->search_end);
        put64(p+48,r->confirmation_start); put64(p+56,r->confirmation_end);
        put32(p+64,r->rate_hz); p[68]=r->channel; p[69]=r->edge; p[70]=r->rx; p[71]=r->verdict;
        put32(p+72,r->reason); put32(p+76,r->search_window_mask);
        put_double(p+80,r->exact_score); put_double(p+88,r->control_score); put_double(p+96,r->margin);
        put_double(p+104,r->cfo_hz); put64(p+112,r->epoch_sample_counter);
        put_double(p+120,r->fractional_offset_samples); put_double(p+128,r->cpu_ms); put_double(p+136,r->wall_ms);
    }
    *written=total;
    return 0;
}

int leo_glrt_frame_legacy_view(const void *input, size_t bytes, const uint8_t **legacy_metadata, size_t *legacy_bytes)
{
    if (!legacy_metadata || !legacy_bytes || !input ||
        bytes<LEO_GLRT_FRAME_HEADER_BYTES || bytes>LEO_GLRT_FRAME_MAX_BYTES) return -1;
    const uint8_t *p=input;
    uint32_t legacy=get32(p+12), count=get16(p+16);
    if (memcmp(p,"LGC1",4) || get16(p+4)!=1 || get16(p+6)!=LEO_GLRT_FRAME_HEADER_BYTES ||
        get32(p+8)!=bytes || get16(p+18)!=LEO_GLRT_RECORD_BYTES || count>LEO_GLRT_FRAME_MAX_RECORDS ||
        legacy>LEO_GLRT_FRAME_MAX_BYTES-LEO_GLRT_FRAME_HEADER_BYTES ||
        LEO_GLRT_FRAME_HEADER_BYTES+legacy+count*LEO_GLRT_RECORD_BYTES!=bytes) return -1;
    *legacy_metadata=p+LEO_GLRT_FRAME_HEADER_BYTES; *legacy_bytes=legacy;
    return 0;
}

int leo_glrt_frame_decode(leo_glrt_frame_v1 *frame, const void *input, size_t bytes)
{
    const uint8_t *legacy_pointer;
    size_t legacy;
    if (!frame || leo_glrt_frame_legacy_view(input,bytes,&legacy_pointer,&legacy)) return -1;
    const uint8_t *p=input;
    uint32_t count=get16(p+16);
    leo_glrt_frame_v1 f={.session=get64(p+24),.generation=get64(p+32),.frame_sequence=get64(p+40),
        .result_sequence_limit=get64(p+48),.dropped_results=get64(p+56),.flags=get32(p+20),
        .legacy_bytes=(uint32_t)legacy,.result_count=count,.legacy_metadata=legacy_pointer};
    memcpy(f.algorithm_sha256,p+64,32); memcpy(f.configuration_sha256,p+96,32);
    p+=LEO_GLRT_FRAME_HEADER_BYTES+legacy;
    for (unsigned j=0;j<count;++j,p+=LEO_GLRT_RECORD_BYTES) {
        f.results[j]=(leo_glrt_classification_v1){
            .sequence=get64(p),.visit=get64(p+8),.valid_start=get64(p+16),.valid_end=get64(p+24),
            .search_start=get64(p+32),.search_end=get64(p+40),
            .confirmation_start=get64(p+48),.confirmation_end=get64(p+56),
            .rate_hz=get32(p+64),.channel=p[68],.edge=p[69],.rx=p[70],.verdict=p[71],
            .reason=get32(p+72),.search_window_mask=get32(p+76),
            .exact_score=get_double(p+80),.control_score=get_double(p+88),.margin=get_double(p+96),
            .cfo_hz=get_double(p+104),.epoch_sample_counter=get64(p+112),
            .fractional_offset_samples=get_double(p+120),.cpu_ms=get_double(p+128),.wall_ms=get_double(p+136)
        };
    }
    if (!valid_frame(&f)) return -1;
    *frame=f;
    return 0;
}
