# Adaptive dual-RX phase product integration

Date: 2026-09-16

## Outcome

The adaptive analysis presentation now treats the GLRT/phase progression PNG as a
versioned, digest-bound analysis product. The Web UI no longer recognizes five
session identifiers or constructs report-asset URLs. It asks the API for the
phase status associated with the selected capture and GLRT sampling policy, then
loads a PNG only when a sealed `ready` manifest names that exact digest.

This is an additive contract. The published adaptive capture, visit-metrics, and
three-figure overview contracts are unchanged.

## Honest applicability states

| State | Meaning | PNG |
|---|---|---|
| `ready` | Qualified simultaneous two-signal RX1−RX0 double-difference evidence was published. | Required |
| `insufficient_signal` | Analysis ran, but no simultaneous pilot pair passed the quality gates. | Forbidden |
| `pending` | The recording contains simultaneous RX0/RX1 samples, but no phase result is published for this GLRT binding. | Forbidden |
| `not_applicable` | The recording retains only one receiver. RX1−RX0 phase cannot be estimated. | Forbidden |

Recent host-adaptive recordings are single-RX and therefore correctly report
`not_applicable`; the API does not imply that a phase estimate exists. The five
historical simultaneous-RX recordings are migrated as `ready` products.

## Binding and read path

Each phase manifest records:

- the capture input-manifest SHA-256;
- the exact GLRT analysis-binding SHA-256;
- the sealed GLRT metrics-manifest SHA-256;
- qualified phase and phase-blind association counts;
- the PNG byte count and SHA-256.

The artifact request repeats the GLRT binding and PNG digest. A mismatch returns
an error rather than serving a nearby file. The API status and PNG handlers read
only bounded, sealed metadata and the requested PNG. They do not read IQ,
decompress visit metrics, run a detector, or infer worker liveness.

## Scientific meaning of the figure

The figure remains the corrected phase-blind-association visualization:

1. passed RX0 GLRT candidates are shown in gray by Starlink channel;
2. simultaneous signal pairs are joined by connectors colored by the wrapped
   two-signal receiver-phase double difference;
3. association uses time and frequency continuity, not phase;
4. wrapped and locally unwrapped double-difference panels show progression only
   across supported arcs; unresolved gaps are not bridged.

The double difference is

\[
  \Delta\Delta\phi(t)
  = [\phi_{1,b}(t)-\phi_{0,b}(t)]
  - [\phi_{1,a}(t)-\phi_{0,a}(t)],
\]

which cancels receiver-common phase at the shared time while retaining the
frequency-dependent spatial/path term. It does not turn separate LNB clocks into
a phase-coherent interferometer, and it does not prove satellite identity.

## Publication pseudocode

```text
capture = inspect(session_id)
glrt = read_sealed_analysis_status(capture, probe_stride_ms)

if glrt.receiver_ids != [0, 1]:
    return NOT_APPLICABLE("requires simultaneous RX0 and RX1")

if no phase manifest exists:
    return PENDING

verify phase.input_manifest_sha256 == capture.input_manifest_sha256
verify phase.glrt_binding_sha256 == glrt.binding_sha256
verify phase.glrt_metrics_manifest_sha256 == glrt.metrics_manifest_sha256

if no pilot pair passed:
    publish sealed INSUFFICIENT_SIGNAL manifest without a PNG
else:
    validate PNG envelope, dimensions, size, and digest
    publish PNG without replacement
    publish sealed READY manifest last
```

## Verification gates

Component tests cover manifest invariants, immutable publication, digest-bound
reads, API GET/HEAD behavior, and the guarantee that the phase API cannot read IQ
or decode GLRT visits. React tests cover ready, absent, and single-RX behavior,
local digest-bound URLs, polling, and sampling-policy changes. The production
verification checks the five migrated historical statuses and images, plus a
recent single-RX adaptive scan returning `not_applicable`.
