#ifndef LEO_ADAPTIVE_LOCAL_SOURCE_PORT_H
#define LEO_ADAPTIVE_LOCAL_SOURCE_PORT_H

#include "local_source.h"
#include "../source/source_port.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct leo_local_source_port leo_local_source_port;

/* source must already be opened and primed. config must be the immutable value
 * used to open source; the adapter copies it and validates every block. The
 * adapter never closes source or owns/restores the radio. */
int leo_local_source_port_create(leo_local_source *source,
    const leo_local_config *config, leo_local_source_port **adapter);
leo_source_port *leo_local_source_port_get(leo_local_source_port *adapter);
/* Returns -EBUSY while a normalized block remains leased. */
int leo_local_source_port_destroy(leo_local_source_port *adapter);
/* Dispose only after common-port cleanup failed with the provider lease still
 * retained. The caller-owned local source keeps that lease and must be closed,
 * which makes the final provider release attempt. */
int leo_local_source_port_abandon_lease(leo_local_source_port *adapter);

#ifdef __cplusplus
}
#endif
#endif
