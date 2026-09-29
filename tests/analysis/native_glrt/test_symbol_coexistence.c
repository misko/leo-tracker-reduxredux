#include "native_glrt.h"
#include "presence.h"

#include <assert.h>
#include <string.h>

int main(void)
{
    /* Linking this test against both implementations is the assertion: the
     * legacy API retains its names while the embedded Wave8 helpers are
     * namespaced inside libleo-native-glrt. */
    leo_presence_destroy(NULL);
    assert(!strcmp(leo_native_glrt_status_string(LEO_NATIVE_GLRT_OK),"ok"));
    return 0;
}
