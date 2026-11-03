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
/* Separate diagnostic API: the existing candidate/result layouts stay intact. */
typedef struct {
    double acquisition_fft_cpu_ms, conditioned_cpu_ms, verification_cpu_ms;
    double epoch_lattice_cpu_ms, final_confirmation_cpu_ms, local_coarse_cpu_ms;
    uint32_t coarse_frames, fine_frames, epoch_frames, anchor_stride, epoch_stride;
    uint32_t conditioned_radius_hz;
} leo_presence_profile;
/* Optional research preprocessing, separate from the original result ABI.
 * Frequency is zero when no spectral candidate was retained. An applied fit
 * changes the working IQ, never the caller's samples or the recording. */
typedef struct {
    int32_t enabled, applied;
    double frequency_hz, spectral_fraction, fitted_power_fraction, cpu_ms;
} leo_presence_nuisance;

/* Exact/control templates are configuration, prepared once outside execution.
 * They must be the complex64 Qin frames promoted to double, for the given edge.
 * A copied immutable template package avoids an embedded Python dependency.
 * Runtime rate support is explicit; unqualified rates fail rather than snap.
 * Template components must be finite and <=16 in magnitude. Input components
 * must be finite and <=1e12; the radio CI16 range is safely inside this bound.
 * All run/diagnostic calls return 0 on success, -1 for unsupported input or
 * geometry. A failed call is unknown evidence, not a negative detection.
 * FE_TONEAREST is required at execution as well as at workspace creation.
 */
leo_presence_workspace *leo_presence_create(
    uint32_t rate_hz, const leo_presence_complex *exact,
    const leo_presence_complex *control, size_t template_count);
void leo_presence_destroy(leo_presence_workspace *workspace);
int leo_presence_get_profile(const leo_presence_workspace *workspace, leo_presence_profile *profile);
int leo_presence_get_nuisance(const leo_presence_workspace *workspace, leo_presence_nuisance *nuisance);
int leo_presence_run(leo_presence_workspace *workspace,
    const leo_presence_complex *samples, size_t count, leo_presence_result *result);
int leo_presence_run_ci16(leo_presence_workspace *workspace,
    const int16_t *interleaved_iq, size_t count, leo_presence_result *result);
/* Experimental proposal reuse: exactly one 20 ms CI16 interval and a local
 * integer timing seed. Searches the full CFO range, preserves tone handling
 * and the existing five-cell/fractional GLRT confirmation. No coarse timing
 * search or local differential refinement is performed. A bad/unbracketed
 * seed is not absence evidence. Result layout and blind entrypoints remain
 * unchanged. Unsupported input leaves result untouched. */
int leo_presence_confirm_ci16(leo_presence_workspace *workspace,
    const int16_t *interleaved_iq, size_t count, int32_t proposal_epoch,
    leo_presence_result *result);
/* Diagnostic surfaces, used for differential qualification of shared kernels.
 * GLRT accepts the acquisition CFO interval [-400000,400000] Hz and fractional
 * offsets in [-2,2] samples, retaining integer epochs separately. */
int leo_presence_coarse(leo_presence_workspace *workspace,
    const leo_presence_complex *samples, size_t count, double *scores);
/* Like the floating diagnostic, no nuisance conditioning is applied. */
int leo_presence_coarse_ci16(leo_presence_workspace *workspace,
    const int16_t *interleaved_iq, size_t count, double *scores);
int leo_presence_glrt(leo_presence_workspace *workspace,
    const leo_presence_complex *samples, size_t count,
    int32_t epoch, double cfo, double offset, double result[3]);
#endif
