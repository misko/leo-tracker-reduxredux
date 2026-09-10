/* Narrow userspace acquisition port. No IIO types or private numerical/IPC
 * structures cross this boundary. All counters denote samples, not host time.
 * API-v1 is experimental until the provider/quality/live-duty gates pass. */
#ifndef LEO_SCANNER_GLRT_H
#define LEO_SCANNER_GLRT_H
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include "adaptive_scan.h"

#define LEO_SCANNER_GLRT_MAX_VISITS 2500u
#define LEO_SCANNER_GLRT_MAX_BLOCK_SAMPLES 1048576u
#define LEO_SCANNER_GLRT_REQUEST_HEADER_BYTES 96u
#define LEO_SCANNER_GLRT_REQUEST_MAX_BYTES 4096u
#define LEO_SCANNER_GLRT_FRAME_MAX_OVERHEAD 704u
typedef struct {
    uint64_t generation;
    uint32_t rx;
    uint8_t algorithm_sha256[32], configuration_sha256[32];
    const uint8_t *legacy_request;
    size_t legacy_bytes;
} leo_scanner_glrt_request_v1;
/* LGO1 wraps, but does not modify/interpret, an existing provider request.
 * Borrowed legacy bytes are valid only as long as the packet. No allocation.
 * Flags/reserved fields are fixed to zero; RX1 only. No runtime file paths. */
int leo_scanner_glrt_request_decode(leo_scanner_glrt_request_v1 *,
    const void *packet, size_t bytes);
ssize_t leo_scanner_glrt_request_encode(const leo_scanner_glrt_request_v1 *,
    void *packet, size_t capacity);
int leo_scanner_glrt_legacy_view(const void *packet, size_t bytes,
    const uint8_t **legacy, size_t *legacy_bytes);

typedef struct leo_scanner_glrt leo_scanner_glrt;
typedef struct {
    uint64_t session, generation;
    uint32_t rate_hz, rx, maximum_visits, maximum_block_samples;
    uint8_t algorithm_sha256[32], configuration_sha256[32];
} leo_scanner_glrt_config_v1;

/* Startup only: preallocate bounded IQ history/result storage and start the
 * isolated worker. Paths come from trusted daemon configuration, never the
 * remote OPENM request. Caller attests the pinned artifact/config digests.
 * The worker and template files must be regular, owned by root/current euid,
 * not group/other writable, and not symlinks. No receive buffer is opened.
 * All methods on one session must be serialized by its acquisition owner. */
int leo_scanner_glrt_open(leo_scanner_glrt **output,
    const leo_scanner_glrt_config_v1 *config,
    const char *worker_path, const char *template_path);

/* Additive explicit positive-only entrypoint. The old open/config ABI and its
 * unqualified behavior are unchanged. A trusted, separately qualified release
 * pins these thresholds in its configuration identity; no absence option. */
typedef struct {
    double minimum_exact_score, minimum_margin;
} leo_scanner_glrt_positive_policy_v1;
int leo_scanner_glrt_open_positive(leo_scanner_glrt **output,
    const leo_scanner_glrt_config_v1 *, const char *worker_path, const char *template_path,
    const leo_scanner_glrt_positive_policy_v1 *);

/* Additive, startup-only opt-in; old open/config/wire layouts stay unchanged.
 * max_occupied_slots limits admission including a partially collected dwell.
 * Pending age includes queueing and computation, measured by CLOCK_MONOTONIC.
 * At admission_age_ms, new checks are skipped; at worker_timeout_ms, only the
 * owned worker is killed without waiting and advisory processing is disabled
 * until a new session. The owner must continue calling block/frame/drain for
 * deadlines to be checked: this is not a separate timer or a hard-RT promise.
 * Pin these values with the trusted release's configuration identity. */
typedef struct {
    uint32_t max_occupied_slots, admission_age_ms, worker_timeout_ms, recovery_blocks;
} leo_scanner_glrt_protection_v1;
int leo_scanner_glrt_enable_protection(leo_scanner_glrt *,
    const leo_scanner_glrt_protection_v1 *);

/* Additive startup-only opt-in, requiring positive policy and protection.
 * Explicit pressure/admission skips carry healthy UNKNOWN scheduler feedback:
 * the advisory owner intentionally did no check, rather than losing feedback.
 * They neither count as misses nor refresh last-positive time. Public records
 * remain unavailable, with zero coverage. Invalid input, worker/clock faults,
 * cancellation and missing/stale feedback keep their existing fault behavior.
 * No setting/ABI/default is changed by merely linking this newer SDK. A caller
 * must pin this policy in a newly qualified bundle configuration before use. */
int leo_scanner_glrt_enable_cooperative_skips(leo_scanner_glrt *);

/* Experimental startup-only fair admission, requiring positive/cooperative
 * protection with all three preallocated slots available. One slot runs, one
 * complete dwell may be held, and one collects. No new IQ allocation occurs.
 * Pending age is bounded in BOTH source time and owner CLOCK_MONOTONIC time.
 * Existing occupancy, admission-age and worker watchdog limits still apply.
 * Fairness uses last dispatch, not last positive: it never changes detections
 * or cooldown. A freshness guard operates only after recent worker overload.
 * Defaults remain unchanged; qualify and identify a new bundle before use. */
typedef struct {
    uint32_t maximum_pending_age_ms, freshness_trigger_ms;
} leo_scanner_glrt_admission_v1;
int leo_scanner_glrt_enable_fair_admission(leo_scanner_glrt *,
    const leo_scanner_glrt_admission_v1 *);
typedef struct {
    uint64_t dispatched, replacements, expired, freshness_skips, pressure_drops;
    uint32_t enabled, pending, running;
} leo_scanner_glrt_admission_stats_v1;
int leo_scanner_glrt_admission_stats(const leo_scanner_glrt *,
    leo_scanner_glrt_admission_stats_v1 *);

enum leo_scanner_glrt_skip_cause {
    LEO_SCANNER_GLRT_SKIP_NONE=0,
    LEO_SCANNER_GLRT_SKIP_PRESSURE=1,
    LEO_SCANNER_GLRT_SKIP_BACKLOG=2
};
/* Acquisition-owner runtime diagnostic, not a persisted/wire contract. Only an
 * explicitly shed check receives a nonzero cause. Requires cooperative opt-in
 * and a known completed visit (EAGAIN while pending). Does not poll, consume an
 * observation, or change policy. Completed fault results keep cause NONE. */
int leo_scanner_glrt_skip_cause(const leo_scanner_glrt *, uint64_t visit, uint32_t *out);

/* Acquisition-owner pressure hint, once per measured block. Nonzero pressure
 * suspends new checks; recovery_blocks consecutive zero hints resume admission.
 * A skipped/partial check is unavailable with zero coverage, never a miss or
 * an invented positive. Already submitted work may finish; no waiting/restart.
 * This does not unlatch the adaptive policy's capture-long uniform fallback.
 * Cooperative skips avoid creating that fault solely from intentional shedding;
 * they cannot clear an already-latched fault. */
int leo_scanner_glrt_capture_pressure(leo_scanner_glrt *, int pressured);

/* Runtime diagnostics only, not a new persisted contract or wire reason.
 * occupied_slots is a momentary shared-pool snapshot, peak_occupied_slots is
 * sampled by the acquisition owner, not a continuous instrumentation trace. */
typedef struct {
    uint64_t backlog_skips, pressure_skips, history_blocks_skipped;
    uint64_t pressure_entries, resumptions, watchdog_trips, clock_faults;
    uint32_t enabled, suspended, disabled, occupied_slots, peak_occupied_slots;
} leo_scanner_glrt_protection_stats_v1;
int leo_scanner_glrt_protection_stats(const leo_scanner_glrt *,
    leo_scanner_glrt_protection_stats_v1 *);

/* Acquisition-owner-only result copy for scheduler feedback. Returns 1 for an
 * observation, 0 if not ready, -ENODATA after the complete terminal inventory,
 * -ENOTSUP without positive opt-in. Does not consume wire results. No waiting;
 * the caller transfers copied observations through its narrow bounded queue,
 * never invokes this non-thread-safe SDK from the hop scheduler thread. */
int leo_scanner_glrt_observation(leo_scanner_glrt *, leo_adaptive_observation_v1 *);

/* Ordered, independently attested hop geometry, potentially arriving after IQ.
 * Visit indices begin at zero. A visit always has 120ms of planned valid time;
 * unavailable/partial input never produces an absence claim. Channel 1..4,
 * edge 0 lower / 1 upper. Geometry and blocks may arrive in either order. */
int leo_scanner_glrt_visit(leo_scanner_glrt *, uint64_t visit,
    uint64_t valid_start, uint64_t valid_end, uint32_t channel, uint32_t edge);
int leo_scanner_glrt_block(leo_scanner_glrt *, uint64_t first_sample,
    const int16_t *iq, size_t samples, size_t stride_shorts, size_t rx_offset_shorts);

/* Stop submitting without waiting for computation. Cancellation resolves
 * incomplete input as unavailable; submitted jobs may still finish normally. */
int leo_scanner_glrt_finish(leo_scanner_glrt *, int cancelled);

/* Encode LGC1 with unchanged opaque legacy bytes and at most four earlier
 * results. Output must not overlap legacy input. No allocation/wait/refill.
 * Frame sequence and consumed results advance only after successful encoding.
 * The original open retains unqualified evidence; open_positive enables only
 * its explicit positive policy. Wire layout and legacy bytes are unchanged. */
ssize_t leo_scanner_glrt_frame(leo_scanner_glrt *, const void *legacy,
    size_t legacy_bytes, void *output, size_t capacity);
/* Only after finish: -EAGAIN while pending; positive metadata-only DRAIN frame;
 * exactly one FINAL, then -ENODATA. No fake IQ and no receive-buffer operation. */
ssize_t leo_scanner_glrt_drain(leo_scanner_glrt *, void *output, size_t capacity);
/* Failure of advisory processing must not change acquisition policy. */
void leo_scanner_glrt_fail(leo_scanner_glrt *);
void leo_scanner_glrt_close(leo_scanner_glrt *);
#endif
