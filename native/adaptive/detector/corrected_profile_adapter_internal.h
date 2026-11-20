#ifndef LEO_ADAPTIVE_CORRECTED_PROFILE_ADAPTER_INTERNAL_H
#define LEO_ADAPTIVE_CORRECTED_PROFILE_ADAPTER_INTERNAL_H

#include "corrected_profile_adapter.h"
#include "corrected_profile_bridge.h"

/* Component-owned conversion seam.  It exists so malformed private receipts
 * can be tested without linking either detector implementation into the test. */
int leo_corrected_profile_convert_result(
    const leo_corrected_profile_result_value *from, size_t expected_rows,
    leo_native_glrt_result *to);

#endif
