#ifndef LEO_ADAPTIVE_USB_SOAPY_PROVIDER_H
#define LEO_ADAPTIVE_USB_SOAPY_PROVIDER_H

#include "usb_source.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Optional provider. Link this symbol only when SoapySDR is available. The
 * selector is a Soapy keyword string such as "driver=rtlsdr,serial=...". */
const leo_usb_provider_ops *leo_usb_soapy_provider(void);

#ifdef __cplusplus
}
#endif
#endif
