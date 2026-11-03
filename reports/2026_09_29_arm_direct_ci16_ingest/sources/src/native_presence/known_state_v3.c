/* V3 preserves V2 scoring and changes only CFO state semantics. */
#include "known_state_v2.c"
#include "known_state_v3.h"

#define KNOWN_CFO_RESIDUAL_SUPPORT_HZ (0.5/SYMBOL_S)

int leo_known_state_v3_measure_ci16(leo_presence_workspace *w, const int16_t *iq,
    size_t count, uint32_t stride, double predicted_epoch, double scored_cfo,
    double expected_physical_cfo, uint32_t recover, uint32_t frame_limit,
    leo_known_state_v3_result *out)
{
    if (!out || !isfinite(expected_physical_cfo) ||
        fabs(expected_physical_cfo-scored_cfo)>KNOWN_CFO_RESIDUAL_SUPPORT_HZ)
        return -1;
    leo_known_state_v3_result result={0};
    if (leo_known_state_v2_measure_ci16(w,iq,count,stride,predicted_epoch,
        scored_cfo,recover,frame_limit,&result.score)) return -1;
    result.expected_physical_cfo_hz=expected_physical_cfo;
    result.cfo_residual_from_scored_hz=result.score.cfo_innovation_hz;
    result.physical_cfo_innovation_hz=
        result.score.tracking_cfo_hz-expected_physical_cfo;
    /* V2 treated the raw GLRT residual as innovation. Replace only that bit;
     * timing failure remains intact. Never clamp either residual or motion. */
    result.score.status&=~LEO_KNOWN_STATE_CFO_REACQUIRE;
    if (fabs(result.physical_cfo_innovation_hz)>KNOWN_CFO_TRUST_HZ)
        result.score.status|=LEO_KNOWN_STATE_CFO_REACQUIRE;
    *out=result;
    return 0;
}
