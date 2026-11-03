#ifndef LEO_ADAPTIVE_RECORDED_SOURCE_H
#define LEO_ADAPTIVE_RECORDED_SOURCE_H

#include "../../scanner/scanner_recorded_plan.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_RECORDED_SOURCE_ABI_VERSION 1u

typedef struct leo_recorded_source_visit_file {
    leo_scanner_recorded_visit visit;
    const char *raw_ci16_path;
    uint8_t raw_sha256[32];
    uint64_t raw_bytes;
} leo_recorded_source_visit_file;

typedef struct leo_recorded_source_config {
    uint32_t abi_version;
    uint32_t sample_rate_hz;
    uint32_t receiver_count;
    uint32_t maximum_samples_per_block;
    uint32_t visit_count;
    const leo_recorded_source_visit_file *visits;
} leo_recorded_source_config;

typedef struct leo_recorded_source leo_recorded_source;

/* Read-only saved-data provider. Configuration and path strings are copied at
 * construction. One visit is loaded and SHA-256 checked at select(), before
 * any block can be returned. No candidate or analysis product is an input. */
int leo_recorded_source_create(const leo_recorded_source_config *config,
    leo_recorded_source **source);
leo_source_port *leo_recorded_source_port(leo_recorded_source *source);
/* Returns -EBUSY while a common-source block remains leased. */
int leo_recorded_source_destroy(leo_recorded_source *source);

#ifdef __cplusplus
}
#endif
#endif
