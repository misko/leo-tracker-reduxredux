/* Bounded synthetic worker-record/wire replay, never IIO or RF. */
#include "../../src/leo/scanner/native_presence/frame_result.h"
#include <stdio.h>
#include <string.h>

int main(void)
{
    const uint32_t rates[]={2500000,5000000};
    const uint64_t starts[]={0,UINT64_C(10000000000000037),UINT64_MAX-600000};
    uint64_t seq=0;
    for (unsigned rate=0;rate<2;++rate) for (unsigned edge=0;edge<2;++edge)
    for (unsigned window=0;window<6;++window) for (unsigned start=0;start<3;++start) {
        uint32_t fs=rates[rate], count=fs/50*6;
        leo_probe_result result={0};
        result.request=(leo_probe_request){.session=71,.generation=9,.sequence=seq,.visit=seq+81,
            .valid_start=starts[start],.valid_end=starts[start]+count,.probe_start=starts[start],
            .rate_hz=fs,.sample_count=count,.rx=1,.channel=3,.edge=edge};
        result.dwell.search_window_mask=63; result.dwell.confirmation_window_mask=1u<<window;
        result.dwell.rank.order[0]=window;
        result.dwell.total_cpu_ms=73.125; result.dwell.total_wall_ms=89.25;
        result.evidence.candidate_count=1;
        result.evidence.candidates[0]=(leo_presence_candidate){.epoch=43,.fractional_complete=1,
            .fractional_offset_samples=-.375,.tracking_cfo_hz=-123456.25,
            .exact_score=.25,.control_score=.125,.margin=.125};
        leo_glrt_frame_v1 frame={.session=71,.generation=9,.frame_sequence=seq+900,
            .result_sequence_limit=seq+1,.legacy_metadata=(const uint8_t *)"synthetic",
            .legacy_bytes=9,.result_count=1};
        /* Synthetic identifiers, not claims about a production algorithm. */
        memset(frame.algorithm_sha256,1,32); memset(frame.configuration_sha256,2,32);
        if (leo_glrt_result_record(&result,NULL,&frame.results[0])) return 2;
        uint8_t output[1024]; size_t written=0;
        if (leo_glrt_frame_encode(&frame,output,sizeof(output),&written) ||
            fwrite(output,1,written,stdout)!=written) return 2;
        ++seq;
    }
    return fflush(stdout) || ferror(stdout) ? 2 : 0;
}
