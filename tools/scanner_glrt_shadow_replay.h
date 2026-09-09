/* Research-only bridge to the public libiio policy/scheduler ports. */
#ifndef LEO_SCANNER_GLRT_SHADOW_REPLAY_H
#define LEO_SCANNER_GLRT_SHADOW_REPLAY_H
#include "../src/leo/scanner/native_presence/scanner_glrt.h"
struct leo_replay_shadow;
int leo_replay_shadow_open(struct leo_replay_shadow **,unsigned rate,unsigned jobs,uint64_t base);
int leo_replay_shadow_start(struct leo_replay_shadow *,double origin_ms);
int leo_replay_shadow_visit(struct leo_replay_shadow *,unsigned visit,uint64_t start,
    uint64_t end,unsigned channel,unsigned edge);
int leo_replay_shadow_offer(struct leo_replay_shadow *,const leo_adaptive_observation_v1 *);
int leo_replay_shadow_finish(struct leo_replay_shadow *);
void leo_replay_shadow_close(struct leo_replay_shadow *);
#endif
