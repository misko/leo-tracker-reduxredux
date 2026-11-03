# USB source-port adapter v1

Date: 2026-09-30

Result: host and ASAN/UBSAN pass; ARM cross-build pass. The adapter maps an
already-open, caller-owned `leo_usb_source` into the common `leo_source_port`
contract without changing source-port v1 structures or ABI.

The adapter supports configured one- and two-receiver streams. Its position is
always a delivered watermark. It never claims a coherent-current position,
UTC, target identity, Fast Lock profile CRC, or an exact gap for estimated or
software counters.

## Selection boundary

Creation requires the additive USB provider capability
`LEO_USB_CAP_RETUNE_VALID_DELIVERY_BOUNDARY`, which also requires RETUNE. The
capability is an explicit promise that no sample delivered after a successful
retune belongs to the preceding tuning:

- with no provider counter, the USB source normalizes the boundary to its
  current software-delivery ordinal only after validating the provider receipt;
- with estimated or exact counters, the provider must return a valid counter
  boundary that does not regress;
- frequency readback alone never creates a boundary;
- a USB receipt has no preceding valid-end time, so the adapter intentionally
  omits common transition time-boundary fields. Per-block timestamps remain
  available with their original authority and uncertainty.

The generic Soapy provider does not advertise this capability. Current
Soapy/RTL adapter creation therefore returns `-ENOTSUP` before retune or other
mutation. This component evidence is not Raspberry Pi, RTL-SDR hardware, rate,
RF, or timing qualification.

## Ownership and failures

The adapter borrows the USB source and is its sole operation owner while alive.
It does not close or restore the source. Cancellation is the only operation
allowed concurrently with a blocked next call; the adapter must not be freed
while either call is running.

USB release is terminal even when the provider reports failure. The adapter
preserves the release error and cleanup ownership: after a common block was
exposed, common cleanup repeats the same error. Ordinary adapter destroy returns
`-EBUSY`, and the caller must abandon the adapter before closing the faulted USB
source. A mapping failure whose emergency provider release also fails retains
this ownership in the adapter, even though no common block was exposed. In that
case common cleanup has no lease to retry; adapter destroy still returns
`-EBUSY`, requiring the same abandon-then-close sequence.

## Component coverage

`test_usb_source_port.cpp` covers:

- stream-info normalization, lease rejection, and provider maximum block size;
- unsupported selection and malformed boundary capability before mutation;
- software, estimated, exact, one-RX, and coherent two-RX mappings;
- delivered-watermark position and counter-valid transitions;
- omission of target, profile CRC, UTC, and transition time claims;
- exact gap/missing-sample propagation and refusal to promote estimated gaps;
- missing, forged, future, and regressing transition boundaries;
- common release failure, cleanup, destroy, abandon, and mapping-error cleanup;
- cancellation and single-lease behavior;
- byte-exact one-RX saved DS9 replay through the common port and
  `WindowAssembler`, using uneven 77,777-sample provider chunks.

The unchanged USB source test also passes in every build.

## Results

| Build | Result | Whole test measurement |
| --- | --- | --- |
| Host | pass | wall 0.01 s, maximum RSS 15,332 KiB |
| ASAN/UBSAN with leak detection | pass | wall 0.03 s, maximum RSS 29,052 KiB |
| ARM Cortex-A9 physical CPU replay | pass | wall 0.115865911 s, CPU 0.115570 s, maximum RSS 13,300 KiB, exit 0 |

Build commands:

```bash
TMPDIR=/var/tmp/leo-usb-port-host-v2-tmp \
  native/adaptive/device/usb/build.sh host /var/tmp/leo-usb-port-host-v2
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
  TMPDIR=/var/tmp/leo-usb-port-sanitize-v2-tmp \
  native/adaptive/device/usb/build.sh sanitize /var/tmp/leo-usb-port-sanitize-v2
TMPDIR=/var/tmp/leo-usb-port-arm-v2-tmp \
  native/adaptive/device/usb/build.sh arm /var/tmp/leo-usb-port-arm-v2
```

Host and sanitizer commands run both component executables against the saved
DS9 fixture. The ARM test command is:

```bash
test-usb-source-port scan-fw-3cfdaa6d75762cad-276.ci16
```

See [source.sha256](source.sha256) for the frozen source and artifact closure.
The exact physical command, fixture binding, and limitations are in the
[ARM receipt](physical-arm/unit.json) and [log](physical-arm/unit.log).
The remaining integration step is an explicitly selected and qualified RTL-SDR
provider that can truthfully advertise the retune delivery-boundary guarantee.
