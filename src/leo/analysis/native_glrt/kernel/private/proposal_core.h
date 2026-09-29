#ifndef LEO_FUSED_PROPOSAL_CORE_H
#define LEO_FUSED_PROPOSAL_CORE_H
#include <stddef.h>
#include <stdint.h>
typedef struct leo_proposal_workspace leo_proposal_workspace;
typedef struct { double fold_ms, correlation_ms, ranking_ms, total_ms; } leo_proposal_timing;
leo_proposal_workspace *leo_proposal_create(const double (*template_data)[2], size_t n, double rate);
void leo_proposal_destroy(leo_proposal_workspace *workspace);
int leo_proposal_top4(leo_proposal_workspace *workspace, const int16_t *raw,
    size_t start, int receiver, int centers[4], int *center_count,
    leo_proposal_timing *timing);
#endif
