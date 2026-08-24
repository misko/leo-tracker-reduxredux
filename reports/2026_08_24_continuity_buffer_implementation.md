# Counter-authoritative Pluto capture: implementation and verification

Date: 2026-08-24  
Status: deployed and post-deployment verified at `058576ec74b7dae9ae3ad2a9798679fcf2c934c3`
Plan: [`cont_buffer.md`](../cont_buffer.md)  
Baseline experiment: [Controlled Pluto refill continuity](2026_08_24_refill_continuity_loopback.md)

## Overview

New dwell and scanner captures can now use the Pluto FPGA sample counter as the
authority for IQ continuity. The implementation no longer assumes that
successive full-length host reads are adjacent in RF time. It resets the RX
buffer at each capture episode, requests and verifies eight kernel buffers,
validates every metadata header twice, drains IQ through a bounded producer /
consumer queue, persists an immutable gap map, and exposes a device-time reader
that returns logical zeros plus an explicit validity mask over missing spans.

The bounded hardware campaign and exact deployed-build canaries passed on both
production Plutos:

- A forced-delay K=1 control produced a counter gap at every tested boundary on
  both radios. This proves that the detector sees the known failure.
- The deployed K=8 paired 60-second dwell proved all 1,144 adjacent refill
  boundaries exact. Each radio stored 150,000,000 observations spanning exactly
  150,000,000 FPGA sample times, with no missing sample, overflow, or queue
  rejection.
- The deployed scanner ran the real four-sweep production burst: 32/32 target
  frames were independently reset and attested, 25 edge observations were
  active, none were inconclusive, and four Standard V4 bundles sealed all 20
  expected PNGs.
- The deployed paired dwell completed in 63.18 seconds versus 102.69 seconds
  for a recent legacy capture. The median V2 scanner sweep took 6.77 seconds of
  capture plus 10.04 seconds of Standard analysis; safe per-target reset and
  attestation dominate the added scanner time.
- All four production selectors name the exact release, API/acquisition/all 20
  workers are running with zero restarts, scanner APIs v1/v2/v3 pass GET and
  HEAD, and capture control remains at the operator's unchanged paused state.

![Continuity red/green and runtime summary](figures/2026_08_24_continuity_buffer_implementation/continuity-buffer-verification.png)

**Figure 1.** Panel A is the controlled 131,072-sample-refill experiment: K=1
lost whole buffers at 572/572 boundaries, while K=2, 4, and 8 had no detected
gap. Panel B compares legacy capture time with the exact post-deployment paired
dwell and median scanner sweep. Dwell capture is faster because radio drain is
no longer serialized behind compression and `fsync`; scanner capture is
deliberately slower because every retune becomes a fresh, metadata-attested
episode. Panel C shows the deployed evidence itself: 572/572 counter boundaries
on each dwell radio and 32/32 reset-bounded scanner frames passed, with zero
gaps, missing samples, or overflow indications.

The compact values behind Figure 1 are preserved in
[`continuity-buffer-evidence.json`](figures/2026_08_24_continuity_buffer_implementation/continuity-buffer-evidence.json),
and the deterministic renderer is
[`report_continuity_buffer_implementation.py`](../tools/report_continuity_buffer_implementation.py).

## Motivation

The earlier analysis found a sawtooth CFO pattern whose discontinuities landed
on application refill boundaries. In the legacy path, every `.rx()` result was
assigned the next synthetic host sample index. A returned array could therefore
have the requested length even when the radio had advanced past samples that
were never delivered. Downstream code interpreted concatenated stored offset
divided by sample rate as physical time, so a real RF-time omission appeared as
a CFO step and biased long/global Doppler-rate estimates.

Host request timestamps reveal slow service, but they cannot tell exactly how
many RF samples were buffered, dropped, or acquired while the host was busy.
The FPGA counter can: for adjacent returned blocks,

```text
expected = previous_first_counter + previous_sample_count
missing  = current_first_counter - expected
```

`missing == 0` proves adjacency inside that capture generation. A positive
value is the exact omitted sample count. A regression, duplicate, invalid
header, counter/sequence disagreement, or unexplained generation change is a
hard integrity failure.

![Stored samples versus FPGA sample time](figures/2026_08_24_refill_continuity_loopback/buffer-count-continuity.png)

**Figure 2.** The original controlled experiment. With K=1, stored time advances
smoothly while the FPGA counter exposes repeated whole-buffer omissions. The
firmware overflow flag remained clear, so continuity must be decided from
counter deltas rather than that flag alone.

## Implemented design

### Metadata runtime and radio port

The release pins `pluto-plus-utils` commit
`30e28464501a1c7706f882fd66ddf147629f6b12` and the ABI-1 metadata libiio source
`c26258bfa33098c2b215e19cf85d448e89499b1a`. The release-local installer builds
and hashes the matching native library and Python binding. Admission happens in
a fresh, scrubbed process; an ambient system libiio or wrong constructor ABI is
rejected before capture.

The metadata session atomically returns IQ with:

- stream generation;
- buffer sequence;
- first FPGA sample sequence;
- metadata flags and overflow bit;
- host request bounds and fitted sample-time intervals;
- actual receiver geometry, sample count, and verified K readback.

The ordinary `.rx()` interface remains useful for legacy/import workflows but
cannot claim sample-loss observability.

### Dwell capture

Live V2 dwells now follow this order:

```text
open and attest
  -> apply and read back RF settings
  -> destroy stale RX buffer
  -> configure K=8 and verify readback
  -> begin a fresh metadata episode
  -> refill producer -> bounded 32-refill queue -> storage consumer
  -> independently revalidate every header while writing
  -> seal timeline, gap map, chunks, and manifest
```

At 2.5 MS/s with dual CI16 receivers, the production 262,144-sample refill is
2 MiB and spans 104.8576 ms. K=8 therefore provides 16 MiB / 0.839 s of kernel
buffering per radio. The 32-refill userspace queue adds 64 MiB per radio. For
two dwell radios the planned total is about 160 MiB.

The producer never blocks behind compression, shard closure, rename, or
`fsync`. Queue-full is terminal: the last rejected metadata header is retained,
the partial bundle is publication-fenced, and a late consumer callback cannot
turn it into a committed recording. Queue capacity, synchronized high-water,
enqueue failures, maximum refill service interval, and terminal rejected-gap /
overflow evidence are persisted.

### Scanner capture

Every target is an independent RF episode:

```text
destroy old buffer -> tune and verify LO -> settle
  -> configure/read back K=8 -> create fresh metadata buffer
  -> capture exactly one frame -> close before the next retune
```

No continuity is claimed across retunes. A valid target must carry a new stream
generation, buffer sequence zero, the requested sample span, and no positive
missing count. The V2 IQ frame, report, metrics, analysis manifest, API, and UI
carry the counter and buffer evidence. An all-target failure is retained as an
immutable sweep report rather than disappearing from scanner history.

### Immutable data and logical zero fill

Observed IQ bytes are never rewritten. Every V2 stream seals a content-addressed
gap map bound to its verified timeline. The public reader provides:

- stored-axis access for the exact observed bytes;
- observed spans with their FPGA coordinates;
- `read_device_span(offset, count)`, where offset zero is the first FPGA sample
  of this capture.

The dense result contains IQ, a boolean validity mask, and continuity-segment
IDs. Missing positions are logical CI16 zero only so fixed-grid consumers can
retain coordinates; `valid=false` is the scientific meaning. The absolute
counter itself is not passed as the reader offset—a canary harness did so once,
and the reader correctly rejected the out-of-range request.

### Fail-loud analysis policy

The first production release takes the conservative policy: a stream with a
counter gap, overflow, queue rejection, unobservable continuity, or corrupt
chain is visibly degraded and is not admitted to stateful Standard or Research
analysis. This guarantees that phase, frame timing, carrier bias, Doppler rate,
and Kalman state do not bridge an invalid interval.

The dense masked reader is ready for a later additive segment-local analysis
release. That future release may analyze valid spans independently, blank
crossing windows, and give each segment independent phase/carrier nuisance
states. It must not reinterpret logical zeros as observed RF. The conservative
quarantine is intentional; this release does not pretend segment-local analysis
is already complete.

## Hardware verification

All RF work was bounded, receive-only, protected by the production global and
per-radio leases, and left capture control at the exact pre-test state:
generation 17, desired `paused`, observed `paused`. TX was never armed; both TX
gains remained -80 dB and all DDS scales were zero.

### Production-refill red/green

The production refill is 262,144 sample times. After a deterministic 350 ms
post-refill delay:

| radio | K=1 gaps | K=1 exact missing | K=8 gaps | K=8 boundaries | overflow flags |
|---|---:|---:|---:|---:|---:|
| `.20` / `5d4d` | 5/5 | 5,242,880 | 0 | 11 | 0 |
| `.21` / `19f2` | 5/5 | 5,242,880 | 0 | 11 | 0 |

Each red-arm delta was 1,310,720 samples, meaning four full 262,144-sample
refills were missing before each returned block. Each green-arm delta was
exactly 262,144. This is a true red/green test: K=1 demonstrates that the
counter path catches loss; K=8 demonstrates the intended mitigation under the
same forced-delay shape.

### Exact deployed one-second smoke

Before the long canary, the installed release captured 2,500,000 sample times
from `.20` as session `canary-final-5d4d-1s-20260824-001`. Its ten refill
headers formed the exact sequence `0..9`; every full boundary advanced 262,144
FPGA sample times; the final partial refill closed the requested span exactly.
K read back as 8, queue high-water was 1/32, maximum refill service interval was
104.065 ms, and gaps, missing samples, overflow, clipping, constant IQ, and
enqueue failures were all zero. The bundle committed in 3.3001 seconds. Its IQ,
timeline, gap-map, compressed, and decompressed digests all reopened cleanly.

### Sustained paired 60-second dwell

| metric | `.20` / `5d4d` | `.21` / `19f2` |
|---|---:|---:|
| observed / device-span samples | 150,000,000 / 150,000,000 | 150,000,000 / 150,000,000 |
| refills / adjacent boundaries | 573 / 572 | 573 / 572 |
| distinct counter delta | 262,144 | 262,144 |
| gaps / missing / overflow | 0 / 0 / 0 | 0 / 0 / 0 |
| queue high-water / capacity | 10 / 32 | 9 / 32 |
| maximum refill service interval | 109.312 ms | 106.902 ms |

This is the exact installed-release canary, session
`canary-final-paired-60s-20260824-001`. It committed in 63.1782 seconds as
manifest
`sha256:ba506305deda171bfa58682f78ad7627438f8f201bcc04b6e69d6fd23c2fd787`.
Independent reopen verified all 18 compressed and 18 decompressed IQ chunk
digests, both timelines, both gap maps, all 1,144 counter boundaries, and the
2.4 GB uncompressed inventory. The two radios overlapped for an estimated
59.9208 seconds; as expected for best-effort independent radios, this is not a
phase-coherent start.

The earlier staging canary also passed with queue high-water 1/32 and a 158.867
ms service interval on `.21`. That interval was longer than one nominal refill
yet produced no counter gap, illustrating why host intervals are telemetry and
the FPGA counter—not elapsed host time—is the continuity oracle.

### Four-sweep scanner burst and Standard products

The exact installed release ran one production-shape burst with four sweeps and
eight targets per sweep. Sweep capture times were 6.5335, 6.5657, 6.9824, and
7.2500 seconds. Every one of the 32 target frames had:

- K requested/readback 8/8;
- reset episodes 1 through 8 within its sweep;
- a unique stream generation and sequence zero;
- exactly 300,000 sample times;
- zero missing samples and no overflow flag;
- LO readback error of 0 or -2 Hz, inside the ±10 Hz gate.

The burst ID is `scan-burst-42e8c4ce197e40b8`; its durable report digest is
`sha256:3323bf8f9ff7a55846b084e30bb25e0f78ad21d5b5b32da71d486ca343f70383`.
It classified 7, 8, 6, and 4 targets active by sweep—25 total—with zero
inconclusive observations. Standard analysis took 10.0470, 10.0818, 10.0395,
and 9.8828 seconds. The four V4 analysis bundles each generated waterfall,
GLRT64, pilot Doppler, pilot carrier tracking, and segment-rate PNGs. All four
IQ bundle digests, all 32 per-frame decompressed IQ digests, every analysis
product digest, and all 20 PNG signatures/digests were independently verified.

## Runtime interpretation

The legacy dwell path serialized radio reading with conversion, compression,
and durable storage. A recent 60-second V1 dwell required 102.694 seconds to
create and finalize. The exact deployed paired V2 dwell required 63.178
seconds, a 39.516-second or 38.5% reduction. More importantly, the FPGA counter
proves that the stored 60 seconds are 60 seconds of device sample time.

Scanner cost moved in the other direction: recent V1 sweeps took 1.86–1.98
seconds; the four deployed V2 sweeps took 6.53–7.25 seconds, with a 6.77-second
median. The additional 4.61–5.37 seconds per sweep is dominated by eight
repetitions of safe destroy/tune/settle/create/attest/close. Standard analysis
then adds 9.88–10.08 seconds per sweep outside the radio lease. Across the
complete burst, radio capture totaled 27.332 seconds and Standard totaled
40.051 seconds; first capture start to durable burst report was 76.159 seconds
including publication and process overhead. This remains comfortably inside
the 180-second scanner cadence.

For a gap-free dwell, the Standard scientific graph is unchanged: continuity
validation and the small gap-map bind occur at input admission, while GLRT,
trajectory, pilot, segment, and presentation work is the same. We therefore do
not assign a synthetic per-path analysis penalty. The measured scanner Standard
times above are the relevant end-to-end check; continuity capture changed radio
occupancy, not the analysis algorithm. A degraded dwell is deliberately refused
rather than paying runtime to analyze across an invalid gap.

## Software verification

The final release passed:

- 1,673 bounded Python tests, with 166 hardware/PostgreSQL/protected-corpus
  cases explicitly deselected;
- the exact `./ops test --release` receipt: 205 gates in 44.8078 seconds;
- protected release qualification at the same SHA: real-corpus, production web
  build, and Chromium end-to-end checks, all passing in 169.9474 seconds;
- strict MyPy across the source tree;
- Ruff lint and format checks;
- all 62 web tests and the production web build;
- release lock, native-runtime installer, manifest/chunk/timeline/gap-map
  digest, and late-publication-fence checks.

Coverage includes hard rejection of a non-integral one-sample ABI-1 gap, exact
reconstruction of one-refill and multi-refill gaps, duplicate, regressing,
reset, overflow-only, and mismatched headers; storage revalidation;
logical zero/mask/segment slicing; terminal gaps; queue-full and hung-`fsync`
shutdown; V1 digest compatibility; fresh scanner session ordering; missing
metadata; stale tuning; and exact K readback.

## Deployment and rollback

Production was cut over from `743216c207c23e23bdc7cc7b9a0729f33db2d3b5`
to `058576ec74b7dae9ae3ad2a9798679fcf2c934c3` with the guarded full-deployment
path. The transaction took 218.3584 seconds and:

1. staged a content-addressed release and built the release-local ABI-1
   metadata runtime;
2. passed exact-revision release qualification before stopping production;
3. preserved the original environment bytes, then atomically selected the V2
   dwell, qualification, soak, and scanner configuration;
4. quiesced every shipped LEO service/timer and all workers, fenced the old
   release's active work, ran the cutover preflight, and switched all four
   selectors;
5. started and verified API, acquisition, and workers 1–20;
6. preserved capture-control generation 17 and the operator's exact paused
   state throughout deployment and receive-only canaries.

After cutover, all 22 runtime processes are active/running with `NRestarts=0`,
all four selectors resolve to the exact release, API backlog is zero queued and
zero running, and v1/v2/v3 scanner latest/history endpoints pass both GET and
HEAD. The web root is healthy. Both production radio locks and the global radio
lock were free after the canaries.

Rollback is a transaction rather than a symlink shortcut. It quiesces the
failed target before restoring the original environment bytes, all four prior
selectors, and prior units; it fences target-release work before starting the
old runtime and re-quiesces if old health verification fails. It never deletes
recordings, artifacts, catalog rows, receipts, or either immutable release, and
never downgrades the database. The root-owned pre-cutover environment snapshot
is `/etc/leo/leo.env.pre-058576ec74b7dae9ae3ad2a9798679fcf2c934c3`, SHA-256
`01aa9f23d7bcc12e9be8314717d51f5e3ce62fd54425048bd621b67df69bac40`.

## Limitations and next steps

- The FPGA counter proves adjacency on the Pluto sample clock; it is not an
  independent UTC clock. Host/fitted sample-time bounds still carry uncertainty.
- Both receiver channels on one Pluto share a counter and acquisition stream.
  They are not independent witnesses of a shared device/transport failure.
- The firmware overflow bit is currently insufficient: known gaps had no flag.
  Counter deltas remain authoritative.
- K=8 is a measured production margin, not a proof against arbitrary stalls.
  Queue-full and sustained-throughput failure therefore remain fail-closed.
- Scanner target isolation costs roughly 0.47 seconds per target in this
  canary. Profiling tune/metadata session setup may reduce this without weakening
  the reset boundary.
- Segment-local Standard/Research analysis over degraded bundles is deliberately
  deferred. The current release quarantines them, while the masked dense reader
  preserves everything needed for a later scientifically explicit implementation.
- Recording V2 currently leaves `producer.source_revision` null. The canaries
  bind build identity through all four immutable release selectors and sealed
  deployment receipts, but a future additive contract should embed the producer
  revision directly in each recording.
- A future externally clocked waveform test can distinguish a pathological
  common TX/RX/counter stall from receive-stream continuity. The present result
  proves delivered RX sample adjacency, which is the property required here.

## Evidence and provenance

The pre-deployment sealed canary acceptance summary is
`c5-canary-acceptance-summary.json`, SHA-256
`262575709a3765ad7a68b6df8d042c39d085797ce21f4b4da4a297b99fe8bbc5`.
Raw canary payloads remain outside Git; this report commits compact derived
evidence and their hashes. The paired-dwell evidence hash is
`ff51ef39ccef00a91c9f2621b235e83e8f361529688ee83d80c23ff71b75dc20`;
the corrected scanner evaluation hash is
`841435da82a3f93a7922a3492c94b1c32b81265fa872d4dbda97250031498756`;
and the scanner Standard-analysis evidence hash is
`21651eebbed187195b762cb872237e1587e2bd5a4455a83ede08c9ebb05add97`.

The exact-release evidence is retained beneath:

```text
/srv/bulk/leo/qualification/continuity-final/
  058576ec74b7dae9ae3ad2a9798679fcf2c934c3/
```

The one-second manifest digest is
`sha256:6bae3cfcb04879813f865b988363079f0d031a7452a50152ea24d063923f45ee`;
the paired 60-second manifest digest is
`sha256:ba506305deda171bfa58682f78ad7627438f8f201bcc04b6e69d6fd23c2fd787`;
and the four-sweep scanner burst digest is
`sha256:3323bf8f9ff7a55846b084e30bb25e0f78ad21d5b5b32da71d486ca343f70383`.
The compact checked-in JSON records all four scanner IQ and analysis manifest
digests rather than relying on mutable path descriptions.

Release and deployment receipts are:

| receipt | result | SHA-256 |
|---|---:|---|
| exact release test, 205 gates | passed | `a90284b2bc2fdd88642960245849e8fe9f10c59a126eb7647fd91bfc3c310620` |
| protected release qualification | passed | `6b88494701218c55e8e473cfc5f413ac0f0149f418ad3f855bbffbe34eceb2fc` |
| guarded full deployment | healthy | `055c82160745e29391630d21be7d60bbf7fa6fdf5fa28c4a2be62ea47cf4eebb` |

The scanner harness initially treated the string `"0"` as truthy when checking
`dds_enabled`. That produced a false blocker in the raw receipt, not an RF
failure. The corrected immutable evaluation documents the mistake; the
installed fail-closed mute check had already verified raw values, -80 dB TX
gains, empty TX channels, and zero DDS scales. No radio rerun was required.
