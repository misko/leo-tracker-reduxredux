#ifndef LEO_ADAPTIVE_CORRECTED_PROFILE_ADAPTER_H
#define LEO_ADAPTIVE_CORRECTED_PROFILE_ADAPTER_H

#include "../scanner/scanner_profile.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct leo_corrected_profile_adapter leo_corrected_profile_adapter;

/* The adapter is a separate corrected-profile composition.  Its linked
 * process must contain the corrected detector archive and must not contain the
 * ordinary detector archive, whose exported symbol names intentionally match.
 * Destroy only after scanner execution and all direct analyze calls stop. */
int leo_corrected_profile_adapter_create(leo_corrected_profile_adapter **out,
    uint32_t sample_rate_hz, const leo_native_glrt_complex *exact_template,
    const leo_native_glrt_complex *control_template,
    size_t template_complex_count);
int leo_corrected_profile_adapter_destroy(leo_corrected_profile_adapter *adapter);

/* configuration_digest is caller authority over the templates and corrected
 * detector closure.  It must be nonzero and is copied into the binding. */
int leo_corrected_profile_adapter_binding(leo_corrected_profile_adapter *adapter,
    const uint8_t configuration_digest[32],
    leo_scanner_profile_detector_binding *binding);

#ifdef __cplusplus
}
#endif
#endif
