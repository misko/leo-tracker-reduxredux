/* Versioned opt-in LIBIIO classification metadata. Legacy bytes are opaque.
 * No allocation, waiting, IIO access, or IQ ownership in this codec. */
#ifndef LEO_SCANNER_GLRT_FRAME_CODEC_H
#define LEO_SCANNER_GLRT_FRAME_CODEC_H
#include <stddef.h>
#include <stdint.h>

#define LEO_GLRT_FRAME_HEADER_BYTES 128u
#define LEO_GLRT_RECORD_BYTES 144u
#define LEO_GLRT_FRAME_MAX_RECORDS 4u
#define LEO_GLRT_FRAME_MAX_BYTES 65536u
#define LEO_GLRT_FRAME_DRAIN 1u
#define LEO_GLRT_FRAME_FINAL 2u
#define LEO_GLRT_FRAME_DETECTOR_FAILED 4u

enum leo_glrt_verdict { LEO_GLRT_UNAVAILABLE, LEO_GLRT_STARLINK, LEO_GLRT_NO_SIGNAL };
enum leo_glrt_reason {
    LEO_GLRT_COMPLETE, LEO_GLRT_WORKER_BUSY, LEO_GLRT_WORKER_FAILED,
    LEO_GLRT_INVALID_INPUT, LEO_GLRT_INCOMPLETE_SEARCH,
    LEO_GLRT_UNQUALIFIED_CLASSIFIER, LEO_GLRT_CANCELLED
};

typedef struct {
    uint64_t sequence, visit, valid_start, valid_end, search_start, search_end;
    uint64_t confirmation_start, confirmation_end;
    uint32_t rate_hz;
    uint8_t channel, edge, rx, verdict;
    uint32_t reason, search_window_mask;
    double exact_score, control_score, margin, cfo_hz;
    uint64_t epoch_sample_counter;
    double fractional_offset_samples, cpu_ms, wall_ms;
} leo_glrt_classification_v1;

typedef struct {
    uint64_t session, generation, frame_sequence, result_sequence_limit, dropped_results;
    uint8_t algorithm_sha256[32], configuration_sha256[32];
    uint32_t flags, legacy_bytes, result_count;
    const uint8_t *legacy_metadata;
    leo_glrt_classification_v1 results[LEO_GLRT_FRAME_MAX_RECORDS];
} leo_glrt_frame_v1;

/* Success is zero. Failure leaves output bytes/structure and written unchanged.
 * Output storage must not overlap frame/input storage. The decoded legacy
 * pointer borrows the supplied packet; records are copied into the output.
 * Wire integers are little-endian; doubles are IEEE-754 binary64, not structs.
 * Encoding a verdict does not qualify the underlying classifier or negotiate
 * permission to send this envelope to a legacy LIBIIO client. */
int leo_glrt_frame_encode(const leo_glrt_frame_v1 *frame,
    void *output, size_t capacity, size_t *written);
int leo_glrt_frame_decode(leo_glrt_frame_v1 *frame, const void *input, size_t bytes);
/* Validate a standalone record before queueing it; zero means valid. */
int leo_glrt_record_validate(const leo_glrt_classification_v1 *record);
/* Structural extraction only: invalid classification semantics need not stop
 * the recorder from validating/forwarding its unchanged legacy metadata. */
int leo_glrt_frame_legacy_view(const void *input, size_t bytes,
    const uint8_t **legacy_metadata, size_t *legacy_bytes);
#endif
