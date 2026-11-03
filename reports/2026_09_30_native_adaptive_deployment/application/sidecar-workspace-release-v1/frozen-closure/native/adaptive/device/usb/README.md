# Portable USB SDR source

`usb_source` is the transport-neutral native receive boundary for a USB SDR on
a Pi or another Linux host. The core is C11 and depends only on libc. A driver
implements `leo_usb_provider_ops`; the core owns validation, one-block leasing,
counter provenance, exact-gap accounting, cancellation, retune receipts, and
cleanup.

The contract does not turn delivery order into a hardware clock. A device with
no counter produces `LEO_USB_COUNTER_SOFTWARE_DELIVERED`, whose value is only
the number of sample-times returned by this source. It cannot reveal data lost
inside a device or driver. `LEO_USB_BLOCK_GAP_EXACT` appears only between two
blocks carrying provider-exact counters. Host arrival is never converted into
a sample timestamp.

Two receiver operation is accepted only when a provider explicitly advertises
both simultaneous and coherent receive channels. CI16 blocks use
sample/receiver/I/Q order. The returned data remains borrowed until
`leo_usb_source_release`; only one block may be leased at a time. A cancel call
may run from a deadline thread while `next` is blocked. All other calls are
single-owner operations.

The optional SoapySDR 0.8 backend is deliberately conservative:

- It enables one receive channel. Generic Soapy metadata cannot prove coherent,
  simultaneous two-channel sampling.
- It reports no hardware sample counter. The core therefore exposes only the
  software-delivered ordinal.
- It exposes a device timestamp only when `readStream` sets `SOAPY_SDR_HAS_TIME`.
  The generic backend declares its uncertainty as `UINT64_MAX`, so it does not
  qualify an exact counter-to-time mapping.
- It reports a Soapy overflow on the next delivered block as an explicit
  discontinuity. It does not invent the number of missing samples.
- It polls `readStream` at 100 ms for bounded cancellation. A global advisory
  lock prevents two instances of this adapter from sharing a USB SDR. Soapy has
  no portable way to exclude unrelated applications; operators must stop them.
- It snapshots sample rate, bandwidth, and center frequency before changing
  them and attempts to restore all three after closing the stream. A restore
  failure makes close fail. Gain is not changed.
- A retune receipt reports the actual read-back frequency but no portable
  post-retune counter or time validity boundary.

Build and test the provider-neutral core:

```sh
native/adaptive/device/usb/build.sh host
native/adaptive/device/usb/build.sh sanitize
native/adaptive/device/usb/build.sh arm
```

Host and sanitizer tests require the checked DS9 CI16 artifact. The fake
provider replays it in uneven blocks through the public `WindowAssembler` and
checks the resulting 20 ms dual-receiver window byte for byte. A missing fixture
is a test failure, not a skip.
The suite also replays each recorded receiver independently through a provider
advertising one channel, software-delivered ordinals and no device timestamp.
Both 20 ms channel views remain byte-identical through uneven blocks. The DS9
fixture rate is not a capability claim for any USB radio.

Build the optional backend when `pkg-config SoapySDR` is available:

```sh
native/adaptive/device/usb/build-soapy.sh
```

The hardware test is intentionally separate and fails unless every requirement
is explicit. It receives one block and therefore must only be run under current
RF authorization:

```sh
export LEO_USB_SDR_SELECTOR='driver=...,serial=...'
export LEO_USB_ALLOW_CAPTURE=yes
export LEO_USB_SAMPLE_RATE_HZ=7500000
export LEO_USB_BANDWIDTH_HZ=6000000
export LEO_USB_BLOCK_SAMPLES=150000
export LEO_USB_FREQUENCY_HZ=1710000000
export LEO_USB_FREQUENCY_ERROR_HZ=2
native/adaptive/device/usb/hardware-test.sh
```

RTL-SDR is the first intended Pi target; the dongle variant and Pi endpoint
remain unspecified, and no USB hardware capture was performed. The source layer
supports one receiver, but the scanner and production detector still require
two, so this is not yet a complete RTL-SDR analysis path. A device-specific
provider is required if the selected radio can
truthfully expose a hardware sample counter, bounded device-time uncertainty,
or coherent simultaneous receivers beyond what generic Soapy can attest.
