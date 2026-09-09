/* Standalone policy stress, also suitable for ASan/UBSan and target replay.
 * Synthetic observations/counters only. No radio, IQ, timing-performance claim. */
#include "../../src/leo/scanner/native_presence/adaptive_scan.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>

int main(void)
{
    uint64_t choices=0;
    for (uint32_t rate=2500000;rate<=5000000;rate+=2500000) {
        for (unsigned mask=0;mask<256;++mask) {
            uint64_t now=(UINT64_C(1)<<53)+217;
            const leo_adaptive_config_v1 config={.session=71,.generation=9,.start_counter=now,
                .rate_hz=rate,.target_count=8,.maximum_visits=2500,
                .warmup_visits=3,.missed_dwells=3,.active_weight=3,.quiet_weight=1,
                .cooldown_ms=2000,.maximum_revisit_ms=3000,.hop_budget_ms=160,
                .maximum_result_age_ms=1000,.unhealthy_limit=3};
            leo_adaptive_scan *s=NULL;
            assert(leo_adaptive_create(&s,&config)==0);
            for (unsigned visit=0;visit<2500;++visit) {
                leo_adaptive_choice_v1 choice;
                assert(leo_adaptive_choose(s,now,&choice)==0);
                assert(choice.visit==visit && choice.target<8);
                assert(choice.reason!=LEO_ADAPTIVE_FAULT_FALLBACK);
                if (visit<24) assert(choice.target==visit%8);
                uint64_t start=now;
                now+=rate/1000*120;
                assert(leo_adaptive_commit(s,start,now)==0);
                const leo_adaptive_observation_v1 observation={.session=71,.generation=9,
                    .visit=visit,.valid_start=start,.valid_end=now,.rate_hz=rate,.rx=1,
                    .target=choice.target,.outcome=(mask&(1u<<choice.target)) ?
                        LEO_ADAPTIVE_DETECTED : LEO_ADAPTIVE_NOT_DETECTED,.healthy=1};
                assert(leo_adaptive_observe(s,&observation,now)==0);
                ++choices;
            }
            leo_adaptive_choice_v1 beyond_limit;
            assert(leo_adaptive_choose(s,now,&beyond_limit)<0);
            leo_adaptive_destroy(s);
        }
    }
    printf("{\"rates\":2,\"activity_masks\":256,\"choices\":%" PRIu64 "}\n",choices);
    return 0;
}
