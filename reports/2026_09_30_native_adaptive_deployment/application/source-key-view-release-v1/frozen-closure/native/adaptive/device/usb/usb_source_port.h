#ifndef LEO_ADAPTIVE_USB_SOURCE_PORT_H
#define LEO_ADAPTIVE_USB_SOURCE_PORT_H

#include "usb_source.h"
#include "../source/source_port.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct leo_usb_source_port leo_usb_source_port;

/* source is borrowed and must outlive the adapter. The adapter is the sole
 * owner of source operations while it exists and never closes or restores the
 * source. Creation returns -ENOTSUP unless retune validity is explicitly
 * guaranteed by the provider capability contract. */
int leo_usb_source_port_create(leo_usb_source *source,
    leo_usb_source_port **adapter);
leo_source_port *leo_usb_source_port_get(leo_usb_source_port *adapter);
/* Returns -EBUSY while a common-port block remains leased. Never destroy while
 * next/cancel or another adapter operation is running. */
int leo_usb_source_port_destroy(leo_usb_source_port *adapter);
/* Use only after common release/cleanup failed and the USB source dropped its
 * provider lease while latching a fault. Dispose the adapter first, then close
 * the caller-owned USB source. */
int leo_usb_source_port_abandon_lease(leo_usb_source_port *adapter);

#ifdef __cplusplus
}
#endif
#endif
