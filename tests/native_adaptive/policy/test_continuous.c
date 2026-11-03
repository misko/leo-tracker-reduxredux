#include "spf-scan-policy.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    struct spf_scan_policy_config c={0};
    struct spf_scan_policy *reference=0,*continuous=0;
    struct spf_scan_choice a,b;
    struct spf_scan_feedback old={0};
    uint64_t now=1000;
    c.session=1;c.generation=2;c.seed=42;c.protocol_version=3;
    c.source_rate_hz=2500000;c.targets=1;c.duration_ms=300000;
    c.dwell_ms=360;c.transition_budget_ms=10;c.maximum_revisit_ms=3000;
    c.feedback_age_ms=1000;c.application_delay_ms=1000;c.decay_ms=3000;
    c.maximum_boost=3;c.baseline[0]=1;c.analysis_digest[0]=77;
    assert(!spf_scan_policy_create(&reference,&c,now));
    assert(!leo_scan_policy_create_continuous(&continuous,&c,now));
    for(unsigned i=0;i<20000;++i) {
        assert(!spf_scan_policy_select(continuous,now,&a));
        assert(a.visit==i);
        if(i<100) {
            assert(!spf_scan_policy_select(reference,now,&b));
            assert(a.target==b.target && a.dwell_ms==b.dwell_ms);
        }
        if(i==0) assert(a.dwell_ms==120);
        if(i>0 && i<19000) assert(a.dwell_ms==360); // Activity survives decay/ledger rollover.
        if(i>=19000) assert(a.dwell_ms==120);
        uint64_t start=now+25000,end=start+(uint64_t)a.dwell_ms*2500;
        assert(!spf_scan_policy_commit(continuous,start));
        assert(!spf_scan_policy_finish_visit(continuous,i,true));
        if(i<100) {
            assert(!spf_scan_policy_commit(reference,start));
            assert(!spf_scan_policy_finish_visit(reference,i,true));
        }
        if(i==0 || i==18999) {
            struct spf_scan_feedback f={c.session,c.generation,i+1,i,start,end,0,
                i ? SPF_SCAN_QUIET : SPF_SCAN_ACTIVE,{0}};
            memcpy(f.analysis_digest,c.analysis_digest,32);
            assert(spf_scan_policy_feedback(continuous,&f,end)==SPF_SCAN_ACCEPTED);
            assert(spf_scan_policy_feedback(continuous,&f,end)==SPF_SCAN_DUPLICATE);
            if(!i) {old=f;assert(spf_scan_policy_feedback(reference,&f,end)==SPF_SCAN_ACCEPTED);}
        }
        struct spf_scan_ack ack;
        while(!spf_scan_policy_take_ack(continuous,&ack)) assert(ack.result==SPF_SCAN_APPLIED);
        if(i<100) while(!spf_scan_policy_take_ack(reference,&ack)) assert(ack.result==SPF_SCAN_APPLIED);
        now=end;
    }
    assert(spf_scan_policy_finish_visit(continuous,0,true)==-ESTALE);
    assert(spf_scan_policy_feedback(continuous,&old,now)==SPF_SCAN_EXPIRED);
    spf_scan_policy_stop(continuous,now);
    assert(spf_scan_policy_select(continuous,now,&a)==-ESHUTDOWN);
    spf_scan_policy_destroy(reference);spf_scan_policy_destroy(continuous);
    puts("{\"status\":\"pass\",\"simulated_visits\":20000,\"ledger_rollover\":true,\"rf_collected\":false}");
    return 0;
}
