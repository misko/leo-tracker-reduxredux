#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "kernel/private/dwell_input.h"
#include "glrt_reuse_prepare.h"

int main(void)
{
#if LEO_GLRT_WIDE_DUAL_PREPARE
    if (!__builtin_cpu_supports("avx2")) return 77;
    const size_t count = 200000;
    int16_t *iq = malloc(count*4*sizeof(*iq));
    if (!iq) return 1;
    leo_dwell_input stock = {0}, candidate = {0};
    for (unsigned test=0; test<3; ++test) {
        for (size_t i=0; i<count*4; ++i) {
            const int16_t cycling = (int16_t)((i*19741u+1091u)%65536u - 32768);
            iq[i] = test==0 ? INT16_MIN : test==1 ? cycling : (i%3 ? 0 : cycling);
        }
        if (leo_dwell_input_prepare_reuse(&stock,iq,count) ||
            leo_prepare_wide_pair(&candidate,iq,count) || stock.count != candidate.count)
            return 1;
        for (int rx=0; rx<2; ++rx) {
            if (memcmp(stock.raw[rx],candidate.raw[rx],count*sizeof(*stock.raw[rx])) ||
                memcmp(stock.normalized[rx],candidate.normalized[rx],
                    2*count*sizeof(*stock.normalized[rx])) ||
                memcmp(stock.prefix[rx],candidate.prefix[rx],
                    (count+1)*sizeof(*stock.prefix[rx]))) {
                fprintf(stderr,"nonidentical input buffer %u rx %d\n",test,rx);
                return 1;
            }
        }
    }
    if (leo_prepare_wide_pair(&candidate,iq,1) != -1 ||
        leo_prepare_wide_pair(&candidate,iq,(size_t)1 << 18) != -1) return 1;
    leo_dwell_input_free(&stock);
    leo_dwell_input_free(&candidate);
    free(iq);
#endif
    return 0;
}
