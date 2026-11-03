# RTL-SDR retune and delivery-boundary audit

Date: 2026-09-30

Status: source-level feasibility only. No USB hardware or RF was used. The
generic Soapy provider remains unchanged and does **not** advertise
`LEO_USB_CAP_RETUNE_VALID_DELIVERY_BOUNDARY`.

## Scope and local source

This audit asks whether a future RTL-SDR-specific use of the existing Soapy
provider can truthfully guarantee that no sample delivered after a successful
retune belongs to the preceding tuning. It does not qualify a dongle, a Pi, a
settling interval, or a production capability.

The reviewed local files were:

| File | SHA-256 |
| --- | --- |
| `native/adaptive/device/usb/usb_soapy_provider.cpp` | `0d3a0f2cda8cc06bdc9c4026f9b142eb71be48468e42fb1d604ce99f761e1d19` |
| `native/adaptive/device/usb/usb_source.h` | `f060f07524234546ea34262d3ebac7ddeb1a605498dd4d774848bb513166ea6e` |
| `native/adaptive/device/usb/usb_source_port.c` | `a084f0418b927507cf095e6e5a85f26f7d6d6aed8a2dc2a79bc848df6ee01770` |

The local provider currently deactivates the existing stream, changes and
reads back frequency, then reactivates the same stream. It intentionally leaves
the post-retune counter and time flags clear. Its cancel operation is a
cooperative atomic flag checked around `readStream`, whose timeout is 100 ms;
it does not itself cancel the Soapy driver's async reader. The source contract
permits only cancel to run concurrently with a blocked acquire. Retune remains
a single-owner operation after acquire has returned and no block is leased.

## Exact upstream sources inspected

The existing optional provider was previously compiled against SoapySDR 0.8.1
without hardware. A future qualified build needs an exact three-library source
closure, rather than only the Soapy ABI version:

| Component | Reviewed version and commit | Relevant source |
| --- | --- | --- |
| SoapySDR | `soapy-sdr-0.8.1`, commit `1cf5a539a21414ff509ff7d0eedfc5fa8edb90c6` | [`Device.hpp`](https://raw.githubusercontent.com/pothosware/SoapySDR/1cf5a539a21414ff509ff7d0eedfc5fa8edb90c6/include/SoapySDR/Device.hpp) |
| SoapyRTLSDR | `soapy-rtl-sdr-0.3.3`, commit `80c93fbe189def3ab68d47a6ad3f813f96d3cb99` | [`Streaming.cpp`](https://raw.githubusercontent.com/pothosware/SoapyRTLSDR/80c93fbe189def3ab68d47a6ad3f813f96d3cb99/Streaming.cpp), [`SoapyRTLSDR.hpp`](https://raw.githubusercontent.com/pothosware/SoapyRTLSDR/80c93fbe189def3ab68d47a6ad3f813f96d3cb99/SoapyRTLSDR.hpp) |
| SoapyRTLSDR current head inspected | commit `6ca357c15cbf676ff30eb8eb445d1e1eac17c136` | [`Streaming.cpp`](https://raw.githubusercontent.com/pothosware/SoapyRTLSDR/6ca357c15cbf676ff30eb8eb445d1e1eac17c136/Streaming.cpp) |
| librtlsdr | `v2.0.3`, commit `797f8143266d983c56d8f35d2d442527529dd8a5` | [`librtlsdr.c`](https://raw.githubusercontent.com/osmocom/rtl-sdr/797f8143266d983c56d8f35d2d442527529dd8a5/src/librtlsdr.c), [`rtl-sdr.h`](https://raw.githubusercontent.com/osmocom/rtl-sdr/797f8143266d983c56d8f35d2d442527529dd8a5/include/rtl-sdr.h) |

The relevant stream lifecycle is unchanged between the reviewed SoapyRTLSDR
release and current-head source. Current head corrects its byte-to-sample tick
increment. That tick is not hardware authority and does not change the retune
finding.

The selected deployment must additionally record the `libusb-1.0` version and
DSO hash, kernel version, Soapy module path/hash, and all three loaded DSO
hashes. Soapy's optional module-version string and `getDriverKey()` cannot
attest which librtlsdr binary was loaded. Runtime `getDriverKey()=="RTLSDR"`
and an explicit `driver=rtlsdr,serial=...` selector are necessary routing
checks, but are not provenance checks.

## What the source proves

The generic SoapySDR 0.8.1 API does not specify a flush operation. Its contract
says that deactivate controls or halts flow and that inactive `readStream`
should time out. It also says the same stream object is not required to be
thread-safe. Those statements alone do not exclude queued pre-retune samples.

The pinned SoapyRTLSDR/librtlsdr implementation has stronger concrete
behavior:

1. `SoapyRTLSDR::deactivateStream` calls `rtlsdr_cancel_async` and then joins
   the async reader thread. The call therefore does not return while that
   reader can still invoke its callback.
2. librtlsdr cancellation cancels outstanding libusb transfers, services
   cancellation events, frees the async transfer buffers, and changes the
   async state to inactive before `rtlsdr_read_async` returns.
3. `SoapyRTLSDR::closeStream` deactivates and clears its userspace FIFO.
4. `setupStream` resets the FIFO indices and creates fresh ring storage.
5. `activateStream` drops a retained partial buffer, calls
   `rtlsdr_reset_buffer`, and only then starts a new async thread. Its first
   acquisition also drains any ring entries present at activation.

Consequently, for these exact sources, the sequence

```text
deactivate and join old reader
close old stream and destroy FIFO
set frequency and verify readback
setup a fresh CS16 channel-0 stream
activate fresh stream
read and discard the qualified settling sample count
return the retune receipt
```

excludes stale **userspace callbacks, libusb transfer objects, partial Soapy
buffers, and Soapy FIFO entries** from later delivery. Closing and recreating
the stream is not strictly required by this implementation, because
reactivation also resets and drains the same stream, but it provides the
clearest generation boundary for testing and review.

This proof assumes the provider's blocked `readStream` call has returned before
retune. It does not make Soapy calls concurrently. The current 100 ms polling
cancel is sufficient to request that return; the owner must wait for completion
before retuning or closing.

## What remains unproved

Two facts prevent enabling the delivery-boundary capability now:

1. SoapyRTLSDR ignores the return from `rtlsdr_reset_buffer` and returns
   successful activation anyway. In librtlsdr v2.0.3,
   `rtlsdr_reset_buffer` ignores the results of both USB register writes and
   always returns zero. A failed endpoint reset therefore cannot be reported
   through the current stack.
2. Resetting queues does not establish tuner lock or analog settling. Neither
   Soapy nor librtlsdr supplies a valid-sample boundary after a frequency
   change.

The source-level sequence therefore proves host-side cleanup but not a complete
device-side validity boundary. A future pinned dependency patch should
propagate both reset-register failures through `activateStream`. Even with that
patch, a selected RTL dongle and tuner still need a measured, explicitly
bounded post-activation discard in samples. Sleeping is insufficient because
samples can accumulate while sleeping; the provider must synchronously read
and drop them.

No capability should be enabled from frequency readback, driver name, or a
successful fake-provider test. A direct librtlsdr provider is not warranted by
this audit. A small reviewed patch to the pinned SoapyRTLSDR/librtlsdr source
closure is the leaner first route if hardware qualification confirms the
Soapy path otherwise works.

## Deferred provider shape

The public `leo_usb_provider_ops` and source-port v1 contracts already express
the required result. No source ABI change is needed. After a dongle and Pi are
selected, keep the generic `leo_usb_soapy_provider()` conservative and add an
explicit RTL-qualified provider/profile with:

- a fixed dependency-manifest digest and selected driver/hardware identity;
- a nonzero post-activation discard count in samples;
- a finite restart/discard deadline; and
- the existing one-RX, no-provider-counter, no-bounded-time authorities.

The concrete configuration surface should be chosen only after the physical
discard envelope is known. Until then an opaque public factory would add an
unqualified knob. A private injected device facade is enough for component
tests without changing public contracts.

On a successful qualified retune, the provider should set the discontinuity
for the first delivered block and return only actual frequency. It should not
forge a counter flag. The existing USB source core can synthesize
`valid_counter == current software-delivered ordinal` only when the explicit
qualified delivery-boundary capability is present. Samples dropped inside the
provider do not advance that ordinal, which remains a delivered watermark and
never becomes a hardware counter.

Any failure after the old stream is stopped faults the source. It should not
attempt to continue on a reconstructed stream. Closing the source must close
any partially created new stream, restore the original sample rate, bandwidth,
and frequency with readback, unmake the device, and release the advisory lock.

## Component test plan

Use a provider-private fake Soapy device facade and generation-tagged buffers.
The success test must observe this exact external call order:

```text
deactivate(old) -> close(old) -> setFrequency(new) -> getFrequency(new)
-> setupStream(RX, CS16, channel 0) -> activate(new)
-> read/drop configured settling samples -> successful receipt
```

The fake `deactivate` must model completion of its async reader. Queue an old
generation callback immediately before cancellation and attempt another after
deactivation; only the first may run, and neither may reach the new FIFO. The
first delivered sample must be new-generation data after the exact discard
count. Also assert that retune is never called with a lease or while a read is
active.

Inject a failure or exception independently at:

- old-stream deactivate/join;
- close;
- set-frequency and frequency readback/coercion;
- fresh setup and activation;
- every settling read, including timeout, overflow, and other read errors;
- closing a partially created stream; and
- each original-configuration restore and readback.

Every failure must produce no valid receipt, no boundary promotion, and a
faulted source. Cleanup must be exactly accounted, and restoration failure must
remain visible. Test the 100 ms cooperative cancel path by blocking a read,
requesting cancel from the allowed second thread, waiting for acquire to return,
and only then invoking cleanup. Non-RTL drivers, unpinned RTL dependency
manifests, zero discard, and unknown hardware profiles must remain unsupported
before mutation.

## Remaining physical qualification

Under a separately authorized bounded hardware test, record exact Pi, kernel,
USB topology, dongle VID/PID/serial, tuner key, firmware where applicable, and
all library/module hashes. Then:

1. Alternate two distinguishable lab signals at the old and new frequencies
   for a predeclared number of retunes. Search every discarded and first
   delivered block for both signatures. Establish the worst observed
   first-new/last-old boundary and choose a discard count with stated margin.
2. Measure deactivate/join, close/setup/activate, discard, and whole-retune
   latency distributions. Confirm the deadline fails closed.
3. Exercise cancel while blocked, USB overflow, unplug/device loss, coerced
   frequency, and cleanup/restoration failures.
4. Verify sustained sample rate, loss/discontinuity reporting, memory, CPU,
   temperature, and one-RX detector/scanner throughput on the selected Pi.
5. Repeat restoration checks after success and every injected/physical failure.

These tests may qualify a software-delivered retune boundary for that pinned
stack and hardware profile. They cannot create an exact hardware sample
counter, exact gap size, bounded UTC mapping, coherent peer receiver, or
Fast-Lock/profile attestation.

## Decision

The Soapy path is viable enough to continue once hardware is selected. The
pinned implementation supplies a real async join and fresh FIFO generation, so
a new direct librtlsdr backend is not yet justified. The capability remains
disabled because endpoint-reset errors are currently hidden and the RTL tuner
settling/discard envelope has not been measured.
