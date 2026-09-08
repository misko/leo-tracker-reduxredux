/* Native single-RX presence experiment. No device, storage, or transport API. */
#ifndef LEO_NATIVE_PRESENCE_H
#define LEO_NATIVE_PRESENCE_H
#include <stddef.h>
#include <stdint.h>

typedef struct { double re, im; } leo_presence_complex;
typedef struct {
    int32_t epoch, fractional_complete;
    double acquired_cfo_hz, fractional_offset_samples;
    double tracking_cfo_hz, exact_score, control_score, margin;
    double acquire_score, verify_score, verify_control_score, conditioned_score;
    double coarse_score, exact_grid[5], control_grid[5];
} leo_presence_candidate;
typedef struct {
    int32_t candidate_count;
    leo_presence_candidate candidates[2];
    double conversion_cpu_ms, coarse_cpu_ms, fine_cpu_ms;
    double fractional_cpu_ms, total_cpu_ms, total_wall_ms;
} leo_presence_result;
typedef struct leo_presence_workspace leo_presence_workspace;

/* Exact/control templates are configuration, prepared once outside execution.
 * They must be the complex64 Qin frames promoted to double, for the given edge.
 * A copied immutable template package avoids an embedded Python dependency.
 * Runtime rate support is explicit; unqualified rates fail rather than snap.
 */
leo_presence_workspace *leo_presence_create(
    uint32_t rate_hz, const leo_presence_complex *exact,
    const leo_presence_complex *control, size_t template_count);
void leo_presence_destroy(leo_presence_workspace *workspace);
int leo_presence_run(leo_presence_workspace *workspace,
    const leo_presence_complex *samples, size_t count, leo_presence_result *result);
int leo_presence_run_ci16(leo_presence_workspace *workspace,
    const int16_t *interleaved_iq, size_t count, leo_presence_result *result);
/* Diagnostic surfaces, used for differential qualification of shared kernels. */
int leo_presence_coarse(leo_presence_workspace *workspace,
    const leo_presence_complex *samples, size_t count, double *scores);
int leo_presence_glrt(leo_presence_workspace *workspace,
    const leo_presence_complex *samples, size_t count,
    int32_t epoch, double cfo, double offset, double result[3]);
#endif
