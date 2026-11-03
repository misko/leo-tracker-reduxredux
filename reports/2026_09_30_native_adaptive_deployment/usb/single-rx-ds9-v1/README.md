# Single-receiver USB source regression

The existing USB core and window assembler pass a new component-owned replay
of each DS9 receiver separately. The fake provider advertises one receiver,
no simultaneous/coherent receiver capability, no hardware counter and no device
timestamp. It delivers 900,000 real recorded sample pairs in twelve uneven
blocks. Each selected receiver's assembled 150,000-sample window matches the
original channel byte for byte. Sample coordinates remain explicitly delivered
ordinals, with no exact-gap or UTC claim. The existing dual-receiver regression
also remains in the suite.

Host and ASAN/UBSAN tests pass. The same suite passes as a CPU-only replay on
PLUTO+ in 0.249 seconds with 13,276 KiB RSS. See [receipt.json](receipt.json),
[unit.log](unit.log), and [device input hashes](inputs.sha256).

This prepares the source boundary for the user's intended RTL-SDR experiment.
It does not execute an RTL-SDR driver, detector, RF capture, or Pi. The fixture's
7.5 MS/s rate belongs to DS9 and is not an RTL-SDR capability claim. Production
source code and published contracts were not changed. Scanner/detector
single-receiver support and USB timing qualification remain outstanding.

Reproduce with `native/adaptive/device/usb/build.sh host OUTPUT` or
`native/adaptive/device/usb/build.sh sanitize OUTPUT`, setting `TMPDIR` to an
available task directory. The build verifies the frozen DS9 input hash before
running the suite. ARM uses the `arm` build mode, followed by
`test-usb-source scan-fw-3cfdaa6d75762cad-276.ci16` on the device.
