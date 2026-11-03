# RTL-SDR single-receiver readiness audit

Date: 2026-09-30

This is a read-only source audit. It used no SDR hardware, RF, network radio,
package installation, or production source change. The current repository has
a reusable one-receiver USB capture boundary, but it does **not** yet have a
one-receiver scanner/detector pipeline or qualified RTL-SDR timing authority.
It must never synthesize a second receiver from the first.

## Current boundary status

| Boundary | Current state | Consequence |
| --- | --- | --- |
| USB source core | `usb_source.{h,c}` accepts one or two receivers and represents missing provider counters as a software-delivery ordinal. | The capture and window-assembly boundary is reusable for one receiver. The ordinal is not a hardware counter. |
| Saved one-RX component evidence | Each real DS9 receiver was independently passed through a one-RX fake provider with uneven chunks and compared byte-for-byte with its source samples. See [single-rx-ds9-v1](single-rx-ds9-v1/README.md). | This qualifies layout, buffering, and software-ordinal behavior only. It does not qualify RTL-SDR hardware, an RTL-SDR sample rate, RF, or timing. |
| Optional Soapy provider | `usb_soapy_provider.cpp` opens RX channel 0 and reports one receiver. It reports no counter authority and no portable post-retune counter/time boundary. | Prefer this provider with the Soapy RTL-SDR module for the first hardware adapter. A retune cannot yet satisfy the scanner selection-boundary contract. |
| Direct librtlsdr provider | Absent. Local `pkg-config` cannot find either `librtlsdr` or `SoapySDR`; no matching system headers were found. An earlier optional Soapy 0.8.1 compile used an explicit temporary SDK and did not access hardware. | Do not add a direct backend until the Soapy path is measured on selected hardware and shows a concrete need. |
| Generic source port | `device/source/source_port.h` can describe one CI16 receiver, `SOFTWARE_DELIVERED`, and a delivered watermark. No USB-to-source-port adapter exists. | A narrow adapter is needed. It must not advertise simultaneous/coherent RX, exact gaps, an exact counter, or UTC. |
| Detector | `native_glrt` is an immutable dual-RX ABI. Its preparation and proposal paths hard-code IQIQ stride four and loop over two receivers. | A new additive ordinary single-RX API is required; the published dual API and results remain unchanged. |
| Scanner | `scanner.cpp` requires two receivers in its config, detector capabilities, source capabilities, block geometry, and energy accounting. It also requires simultaneous/coherent RX and an exact selection boundary. | There is no one-RX scanner today. A versioned/additive path is required; legacy v2 behavior remains dual-RX. |
| UTC projection | `timing/timebase.hpp` explicitly rejects software delivery ordinals and host-arrival time as exact counters. `ingest.cpp` also binds live events to nonzero Fast Lock profile attestations. | RTL detections can initially be recorded with source-relative coordinates, but cannot become qualified UTC observations/location evidence. Do not infer UTC from callback arrival or invent a Fast Lock CRC. |

## Detector distinction and approved narrow seam

The private presence engine is not an equivalent one-receiver version of the
deployed detector. Its candidate/nuisance budget differs from the ordinary
`native_glrt` pipeline. Wrapping `leo_presence_run_ci16` would therefore create
a separate research algorithm rather than preserve deployed behavior.

The lean additive path is a `single_rx_glrt` ABI that retains the ordinary
proposal, tracked-center, regional full-search, fine-refinement, and maximum
eight-candidate behavior:

- parameterize proposal input by scalar stride/receiver offset; the current
  scalar and NEON code in `proposal_core.c` assumes stride four and offset
  `2*receiver`;
- prepare exactly one raw/normalized/prefix lane instead of the two fixed lanes
  in `dwell_input.h`;
- reuse `leo_full_search_run_prepared_with_fine_workspace_mode`; the underlying
  CI16 full-search entry point already accepts a scalar stride of at least two;
- compile with the same scientific flags in `detector/build.py`, including the
  eight-frame proposal budget, fixed CI16 coarse scale, FP32 coarse path,
  conditioned screen, refinement mode 2, FFTW, and the qualified NEON path;
- advertise `receiver_count=1` and `peer_recovery_available=0`. A request for
  peer recovery must return explicit unavailable/unsupported status before
  analysis. It must never copy RX0 into a fabricated RX1 lane;
- keep every existing `leo_native_glrt_*` symbol, capability, input layout, and
  result unchanged. Context ownership remains one operation at a time, with
  `BUSY` on same-context contention and destruction only after its worker joins.

The single API may reuse the existing result row/candidate structures if its
own capability contract fixes `receiver_id=0`; it must not reuse the static
dual capability response as though it described one receiver.

## Minimal implementation sequence

1. **Ordinary one-RX detector.** Add the separate detector API described above.
   Component tests compare it with each receiver filtered from an ordinary
   dual-RX run over identical saved data, field by field across all rows and
   candidates. Also test peer-unavailable behavior, stride/layout rejection,
   context contention/lifetime, and unchanged dual regression output.
2. **USB source-port adapter.** Add `usb_source_port.{h,c}` beside the existing
   source port. Map leases, cancellation, discontinuities, receiver count, and
   software-delivery coordinates without upgrading their authority. A
   well-formed one-RX source paired with a legacy dual detector should return
   unsupported before selecting/retuning; malformed zero or greater-than-two
   receiver counts remain invalid.
3. **Retune boundary.** For generic Soapy, deactivate, retune/read back, reactivate,
   and discard explicitly bounded settling data before releasing a software
   boundary. Until that behavior is provider-qualified, selection is
   unavailable. The boundary remains software-relative and is not an exact
   device counter.
4. **Additive one-RX scanner.** Generalize byte geometry to
   `receiver_count * 2` CI16 scalars per sample and route one-RX detector
   capabilities explicitly. Preserve the old dual entry points and v2 event
   contract. Tests use guard regions and uneven blocks to catch residual
   four-scalar indexing, and prove unsupported peer/source combinations fail
   before a retune or detector call.
5. **Separate timing/ingest authority.** Add a versioned non-Fast-Lock source
   identity only when selected RTL hardware supplies a qualified clock/timing
   solution. Until then, retain source-relative recording and detector evidence
   and mark UTC/location unavailable.
6. **Hardware qualification.** Select an actual RTL-SDR model, install its
   provider outside this audit, then run an explicitly authorized bounded test
   for rate stability, dropped samples, retune discard, frequency readback,
   cancellation, restoration, and memory/CPU behavior. None is claimed here.

## External API constraints

The official [Osmocom RTL-SDR header](https://raw.githubusercontent.com/osmocom/rtl-sdr/master/include/rtl-sdr.h)
defines asynchronous delivery as a byte buffer plus byte length and caller
context. It provides cancellation and rate/frequency readback, but the callback
does not carry a hardware sample counter or timestamp. A direct provider would
therefore still expose a software delivery ordinal unless a separate qualified
device-specific authority exists. It would also have to convert unsigned
8-bit interleaved IQ to CI16 explicitly and attest the conversion; it cannot
claim native CI16 hardware samples.

The [RTL-SDR Blog V4 datasheet](https://www.rtl-sdr.com/wp-content/uploads/2024/12/RTLSDR_V4_Datasheet_V_1_0.pdf)
is only a concrete model example: it describes an 8-bit ADC and a stated stable
2.56 MHz rate (with higher rates potentially dropping samples). No V4 device
has been selected, so those properties and that rate are not project
requirements or qualifications.

## Audited source closure

| File | SHA-256 |
| --- | --- |
| `native/adaptive/device/usb/usb_source.h` | `40278ebdf90d05474f5936184befaddcfa1e913c278700a7e5a1fb2d01420475` |
| `native/adaptive/device/usb/usb_source.c` | `738548433cff15508d130e903f5c38152661a2fa3c9fc1b292736676f8cf667e` |
| `native/adaptive/device/usb/usb_soapy_provider.cpp` | `0d3a0f2cda8cc06bdc9c4026f9b142eb71be48468e42fb1d604ce99f761e1d19` |
| `native/adaptive/device/source/source_port.h` | `554a7b5640eb5582b384a0ea4a7d6c6848bcaaf5762c2d17664fb208c277e4a5` |
| `native/adaptive/device/source/source_port.c` | `688493b3c406539ca80b25fb65ffeeb68cf97713c96c25f3a841c8c6b89073ef` |
| `native/adaptive/scanner/scanner.cpp` | `432de57de05871cb2b9ca92f5382080b2f934357a82b539188482219104a851a` |
| `native/adaptive/scanner/scanner.h` | `0edb7e5eefd187264ad4d90cca4589568e66130798d2b3a5addeda43e014d61c` |
| `native/adaptive/detector/native_glrt.c` | `696d1432ed3599cdaf4c6fcef3008b4d67bdb1d5ae5f0336523762fa652f7340` |
| `native/adaptive/detector/native_glrt.h` | `a9a41bb89e9f896d37ae3092b339c83ae9d09a652b16cab67cad8010e87c72c9` |
| `native/adaptive/detector/kernel/private/dwell_input.h` | `4bbc82c77598fccd76732c4903e982c9cbfe950892ac8bdd61edf1e8b4609abf` |
| `native/adaptive/detector/kernel/private/proposal_core.c` | `f874b227376bfe3579455d5588d6a187a67a07812a9e54ee6ab7046f2b31482e` |
| `native/adaptive/detector/kernel/private/full_search.c` | `90e1d49f7bc4ef1ed5e025e02fb23171b3c58e56cc49db1d19d8799e66eca52f` |
| `native/adaptive/detector/kernel/private/native_presence/presence.c` | `571cc7bed8c746981f8e72705133959ba2ff615a81dca760530371ed18980bfe` |
| `native/adaptive/detector/build.py` | `df246fb1d2159d781f8c159fd04b68a6b9fab390d183fc52a657ed6ca5f834d0` |
| `native/adaptive/timing/timebase.hpp` | `96c6990079ee4347b87e90a7a274f849f4d3707f5187f74045c37a926d75f8af` |
| `native/adaptive/timing/timebase.cpp` | `df2425f3219ba80a0c2a856e81bfae081240ce335999776c9b9bf4af5c4bd301` |
| `native/adaptive/ingest/ingest.cpp` | `e8f4aa1c1de08868566fd821c95cc06b65f5747e7d8e4cb1f605652031625bd5` |

The local dependency checks were:

```text
pkg-config --modversion librtlsdr  # package not found
pkg-config --modversion SoapySDR   # package not found
```

The earlier optional Soapy compile and its no-hardware limitation are retained
in [USB qualification](qualification.json). No build or runtime result in this
report claims a selected RTL-SDR or Raspberry Pi configuration.
