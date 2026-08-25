# 3 MS/s and 5 MS/s capture-mode plan

Date: 2026-08-25
Status: implemented in software; hardware qualification and cutover pending
Branch: `codex/3m-5m-sample-modes`
Base: `origin/main` at `4be5f6c49036264adb3809a3084278607e3ac725`

## Outcome

The implementation adds the two rates without making a claim that the hardware
evidence does not support. The production policy is an exact three-profile
pool: every ordinary dual-radio dwell uniformly selects one persisted profile
from 2.5 MS/s,
3 MS/s, and 5 MS/s. Selection occurs once per logical dwell, and every retry
of that dwell retains the selected profile.

- **2.5 MS/s** remains the existing science-capable profile in the pool.
- **3 MS/s** is a candidate sustained-contiguous transport mode, but its
  ordinary-dwell profile remains `CAPTURE_ONLY` until a separately versioned
  scientific path is qualified.
- **5 MS/s** is an experimental `CAPTURE_ONLY` segmented mode. It records every
  observable segment and exact loss evidence, but is never called or
  configured as sustained contiguous.

The ordered pool, its exact profile identities, and its selection policy are a
production-cutover-reviewed configuration. Directory discovery, wildcard
membership, or treating every V2 profile as eligible is prohibited.

A separately named, short 5 MS/s burst mode can be added later if a bounded
single-radio Leo capture is qualified. The current short transport result is
encouraging, but it is not yet full-recorder evidence and must not be combined
with the failed sustained two-radio result.

## Evidence boundary

The hardware report in
`reports/2026_08_25_pluto_dual_radio_contiguous_transport_verification.md`
establishes the following for paired RX0/RX1 CI16, 262,144-sample refills, the
two tested Pluto+ radios, and FPGA sample-sequence metadata:

| Transport case | 3 MS/s | 5 MS/s |
|---|---|---|
| Two simultaneous radios, direct USB, 60 s | zero loss | not tested sustained |
| Two simultaneous radios, native IP/TCP, 60 s | zero loss | loss on both radios |
| One radio at a time, native IP/TCP, short cell | zero loss | zero loss |
| Complete Leo K=8 queue, compression, and durable storage | not yet tested | not qualified |

The runtime modes therefore describe an evidence envelope, not the AD9361
configuration range. `RadioCapabilities.maximum_sample_rate_hz` must continue
to report the hardware limit; it is not a gapless-transport limit.

Leo's production Pluto source currently supports native `ip:<address>` libiio
contexts only. Direct USB remains a qualification/control transport unless USB
runtime support is requested as a separate feature.

## Mode definitions

Use existing content-addressed `CaptureProfileV2` documents as the mode
definitions. Do not add a sample-rate enum or mutate the V1/V2 profile
contracts: they already persist rate, bandwidth, duration/sample count, refill
geometry, K, userspace queue capacity, metadata requirement, and continuity
policy.

### 3 MS/s qualification and capture-only dwell

The implementation adds two immutable profiles:

1. `hardware-canary-3m-60s-contiguous-v2`
   - `sample_rate_hz: 3000000`
   - dual RX, 262,144-sample refills, K=8, queue=32
   - device metadata required
   - `continuity_policy: require_contiguous`
   - `QUALIFICATION` tag so it cannot create an automatic science run
2. `starlink-ch4-lower-3m-60s-capture-v2`
   - the same receive-buffer geometry
   - `continuity_policy: allow_segments`, so an unexpected gap is preserved
     and reported rather than discarding the rest of the dwell
   - `CAPTURE_ONLY` until a 3 MS/s science path is separately qualified
   - participates in the reviewed ordinary-dwell production pool

The operational profile succeeds only when every stream is complete and has
zero missing samples, gaps, overflow observations, enqueue failures, and
terminal rejected refills. `allow_segments` changes salvage behavior, not the
definition of success: a gapped stream remains partial and its session remains
degraded.

### Experimental 5 MS/s segmented capture

The implementation adds `starlink-ch4-lower-5m-60s-segmented-v2` with:

- `sample_rate_hz: 5000000`;
- dual RX, 262,144-sample refills, K=8, queue=32;
- device metadata required;
- `continuity_policy: allow_segments`;
- `EXPERIMENTAL` and `CAPTURE_ONLY` tags; and
- membership in the reviewed ordinary-dwell production pool only as this exact
  segmented profile identity.

This mode is useful because loss is exact and reviewable. It is not a promise
that 300,000,000 adjacent device sample instants will reach storage.

### Optional 5 MS/s bounded burst

Do not ship this as contiguous in the first increment. If the intended use is
scanner-like capture, add a separately named profile such as
`hardware-canary-5m-120ms-burst-v2` only after the full Leo path proves the
exact bound on each radio. It would contain 600,000 sample instants per radio
at 120 ms and use `require_contiguous`.

The qualified statement must include maximum duration, radio count, receiver
count, transport, refill geometry, host, and exact radio identities. A short
single-radio result must never unlock sustained or simultaneous two-radio use.

### Bandwidth is independent

Do not derive `bandwidth_hz` from `sample_rate_hz`. The first recorder canary
should retain the existing 2.5 MHz analog bandwidth to isolate transport and
storage behavior. Rate-matched 3 MHz or 5 MHz bandwidths should be separate
profile revisions and require RF passband, aliasing, and scientific recovery
tests. This prevents a transport change from silently becoming a different
scientific observation.

### Ordinary production dwell selection

The exact ordered production pool is:

1. `starlink-ch4-lower-2p5m-60s-continuity-v2`
2. `starlink-ch4-lower-3m-60s-capture-v2`
3. `starlink-ch4-lower-5m-60s-segmented-v2`

The runner validates every member before starting, chooses each member with
probability 1/3 for a new ordinary dual-radio dwell, and then compiles and
persists only the selected profile revision in that dwell's capture plan and
manifest. Selection occurs outside the retry loop. Backpressure, a busy-radio
conflict, lease expiry, or another retryable failure must reuse the selected
profile name and pool identity; it must not draw again and bias the rate mix.
A new terminally distinct dwell receives a new selection.

Durable scheduling stores the selected profile beside the complete candidate
pool and `uniform_per_dwell` policy before radio execution. Non-durable
scheduling retains the pending selection until that logical dwell succeeds or
fails terminally. Tests use an injected selector and durable payload replay;
they do not use flaky statistical assertions.

This policy applies only to ordinary dual-radio recording dwells. Explicit
one-shot captures, qualification canaries, and soak workflows continue to use
their requested single profile. Scanner scheduling, scanner configuration,
scanner sample geometry, and post-dwell scanner analysis are unaffected; a
scanner run neither selects from nor changes the recording profile pool.

## Implemented design and remaining gates

### 1. Profiles and dwell selection are implemented

- The new V2 YAML documents compile through the existing profile directory;
  every 2.5 MS/s profile remains byte-for-byte intact with its pinned digest.
- The scheduled acquisition service emits one repeated exact `--profile`
  argument for each member of the ordered three-profile pool above.
- Qualification, canary, soak, and explicit one-shot entry points remain
  single-profile unless separately reviewed.
- `profiles list/show/validate` exposes the new profiles. Repeated `--profile`
  values select uniformly once per ordinary dwell; a single value preserves
  existing behavior. No API or database migration is required.

### 2. Capture-only intent fails closed

Automatic processing excludes qualification, calibration, acceptance, and
`CAPTURE_ONLY` captures and refuses degraded manifests. A clear diagnostic
prevents a committed 3 MS/s or gapless experimental 5 MS/s recording from
entering a pipeline whose published acceptance contracts are frozen at
2.5 MS/s.

Keep explicit offline research possible. Standard/WP11 promotion remains
unavailable until the input rate is supported by a versioned scientific path.

### 3. Strict rate qualification is implemented

Do not weaken or mutate `AcquisitionQualificationReceiptV1`; its general 95%
success policy is not strict enough to promote a continuity mode. The published
`ContiguousRateQualificationReceiptV1` also remains immutable. The additive
`ContiguousRateQualificationReceiptV2` binds the independent USB-control
identity, overlap, and restoration evidence in addition to:

- profile revision and capture-plan digests;
- Leo, pluto-plus-utils, Python binding, and native libiio identities;
- host identity and native transport route;
- radio IDs, serials, firmware, and URIs;
- requested and applied rate/bandwidth;
- receiver count, refill samples, K, and queue capacity;
- requested, observed, and device-span sample counts;
- gap map, missing samples, overflow, enqueue failures, terminal rejection,
  queue high-water, and maximum refill service interval; and
- recording manifest, chunk, and continuity-evidence digests.

The strict policy is all-or-nothing: successful fraction 1.0 and every loss or
integrity counter zero. A sustained-contiguous claim consumes an exact receipt,
not a profile name or a host-throughput measurement. Including the exact 5 MS/s
segmented profile in the reviewed pool is not such a claim: its gaps remain
truthful degraded evidence and can never satisfy a contiguous receipt.

### 4. Production cutover remains gated

- The production cutover verifier binds the exact ordered three-profile pool,
  rejects missing, duplicate, reordered, or additional members, and verifies
  the reviewed revision digest and capture semantics of each member.
- A 3 MS/s production-pool selection requires an exact matching rate-
  qualification receipt for the deployed host, radios, software, profile, and
  transport. It remains `CAPTURE_ONLY` regardless of a clean transport result.
- The verifier accepts 5 MS/s only as
  `starlink-ch4-lower-5m-60s-segmented-v2` with `allow_segments`, 2.5 MHz
  analog bandwidth, and `CAPTURE_ONLY`/`EXPERIMENTAL` tags. It rejects 5 MS/s
  as a sole default, contiguous mode, or science-eligible profile.
- Do not silently broaden the pool to “any V2 profile.” Pool membership and
  its cutover evidence are exact, reviewed production configuration.

### 5. New-rate science remains a separate increment

The acquisition and persistence contracts are rate-generic, but published
WP11, trusted acceptance, CFO de-aliasing, Doppler, and campaign evidence pins
2.5 MS/s and 150,000,000-sample dwells. Those contracts and golden evidence
must stay unchanged.

Initially, 3 MS/s and 5 MS/s recordings are capture-only. Before enabling
Standard analysis, choose and qualify one of these additive paths:

- For observations whose usable analog bandwidth remains at most 2.5 MHz,
  create a provenance-bearing normalized IQ product. Use rational 5/6
  resampling for 3 MS/s to 2.5 MS/s and decimation by 2 for 5 MS/s to
  2.5 MS/s. Persist the source digest, rational ratio, filter identity/digest,
  group-delay mapping, output digest, and validity intervals.
- For a genuinely wider 5 MHz observation, create a new versioned wideband or
  channelized analysis lane. Do not silently discard the outer spectrum by
  downsampling it into the existing 2.5 MHz lane.

Gaps must split validity intervals and invalidate the resampler guard region;
they must never be interpolated into apparently contiguous science IQ.

## Capacity model

Paired CI16 RX is 8 bytes per sample instant per radio.

| Geometry | 3 MS/s | 5 MS/s |
|---|---:|---:|
| Payload per radio | 24 MB/s | 40 MB/s |
| Payload for two radios | 48 MB/s | 80 MB/s |
| Refill period at 262,144 samples | 87.381 ms | 52.429 ms |
| K=8 RF-time cushion | 0.699 s | 0.419 s |
| Queue=32 RF-time horizon | 2.796 s | 1.678 s |
| Raw bytes, two radios, 60 s | 2.88 GB | 4.80 GB |
| Refills per radio, 60 s | 687 | 1,145 |
| Metadata reserve, two radios at 4,096 B/refill | 5,627,904 B | 9,379,840 B |

The memory allocation remains about 80 MiB per radio because refill and queue
counts do not change. More buffering cannot fix a sustained transport deficit;
it only covers bounded consumer stalls.

Require an incompressible writer benchmark of at least 72 MB/s before 3 MS/s
promotion (1.5 times its 48 MB/s aggregate input). Treat 100 MB/s as the
minimum characterization target for a two-radio 5 MS/s experiment; transport
continuity is still an independent gate.

## Portable test plan

### Profile and contract tests

- Load all new YAMLs as `CaptureProfileV2` and assert unique revision digests.
- Resolve 60 seconds to exactly 180,000,000 samples at 3 MS/s and 300,000,000
  at 5 MS/s.
- Assert dual RX, 262,144 refill samples, K=8, queue=32, metadata required,
  explicit bandwidth, and the intended continuity policy/tags.
- Assert all existing 2.5 MS/s profile digests and manifest round trips remain
  unchanged.
- Assert the admission estimates shown in the capacity table and verify that
  insufficient storage rejects the plan before either radio is opened.

### Pluto adapter tests

- Parameterize configure/readback at 3 and 5 MS/s, including bandwidth.
- Reject an applied rate or bandwidth that differs from the request.
- Keep missing metadata capability, ABI mismatch, reset failure, and K readback
  mismatch as hard preparation failures.
- Assert the adapter reports the hardware maximum independently of the
  station's qualified continuity envelope.

### Coordinator and storage tests

- Complete clean fake-counter captures at 3 and 5 MS/s and verify exact
  requested/observed/device-span closure, including a partial final refill.
- Inject a gap at 3 MS/s under `require_contiguous`; persist the offending
  counter header, stop at the boundary, and produce only degraded evidence.
- Inject gaps at 5 MS/s under `allow_segments`; continue to the requested
  device span, seal exact gap intervals/missing counts, and remain degraded.
- Cover overflow without a counter jump, full userspace queue, consumer crash,
  cancellation, and one failed peer beside one clean peer. None may produce a
  false committed manifest or nonzero guaranteed overlap.
- Round-trip both rates through recording storage, catalog reconciliation, API
  presentation, and manifest/chunk/gap-map verification.

### Analysis eligibility and numerical tests

- Assert `CAPTURE_ONLY`, `QUALIFICATION`, and degraded recordings do not create
  automatic Standard runs.
- Assert frozen WP11 and trusted-acceptance contracts continue to reject 3 and
  5 MS/s inputs.
- Assert the ordinary-dwell profile pool does not change scanner scheduling,
  scanner configuration, sample geometry, or analysis inputs.
- For normalized IQ, test impulse/time origin, passband amplitude and phase,
  stopband rejection, rational output length, group delay, chunk-boundary
  invariance, deterministic output digests, and gap guard invalidation.

### CLI and deployment tests

- `profiles list/show/validate` displays both rates and their descriptions.
- Explicit manual capture accepts each new profile and single-profile runs
  preserve existing behavior.
- Repeated `--profile` values validate the complete pool before radio access,
  and an injected selector proves every pool member can be chosen without a
  statistical test.
- Each new logical dwell makes one selection. Busy-radio, backpressure, and
  durable-operation retries retain the selected profile; a subsequent dwell
  makes a new selection.
- Durable scheduled payload round trips bind the selected profile, complete
  pool, and `uniform_per_dwell` policy.
- The scanner follows its existing schedule and configuration regardless of
  which recording profile is selected.
- The cutover verifier accepts only the exact reviewed three-profile pool,
  requires the 3 MS/s strict receipt, and rejects any configuration that makes
  5 MS/s contiguous or science eligible.
- A gapless experimental 5 MS/s capture still stays out of automatic science
  because its eligibility is profile-scoped, not inferred from one lucky run.

Suggested portable gate:

```bash
uv run pytest \
  tests/contracts/test_profiles.py \
  tests/acquisition/test_pluto_adapter.py \
  tests/acquisition/test_continuity_capture_v2.py \
  tests/qualification/test_acquisition_qualification.py \
  tests/cli/test_acquire_cli.py \
  tests/cli/test_capture_supervisor.py \
  tests/cli/test_automatic_lane_selection.py \
  tests/deploy/test_production_cutover.py
```

Then run the repository gates:

```bash
./ops test
./ops test --all
./ops test --release
```

## Bounded hardware qualification

The implemented component-owned opt-in harness is
`tests/acquisition/test_pluto_rate_modes_hardware.py`, marked
`@pytest.mark.hardware`. It remains inert without the exact bounded-RX
authorization phrase and its complete environment inventory. It accepts only
literal native addresses in `192.168.1.0/24`; discovery cannot select a USB
gadget address.

The harness loads the committed
`hardware-canary-3m-60s-contiguous-v2` profile, whose reviewed revision digest
is `sha256:03d31584df57dc6361f067018cc609c5b3380fbafeab26563cdd2ace6d233c97`.
For the fixed ordered production radio IDs `radio_pluto_5d4d` and
`radio_pluto_19f2`, it compiles plan digest
`sha256:ddacc29f61c2d7e0b30e631ec84b91b737f7fecbe2d63015443b4ca588ca998e`.
The production cutover verifier additionally binds those IDs to the exact
serial/URI pairs:

| Radio ID | Serial | Native URI |
|---|---|---|
| `radio_pluto_5d4d` | `1040005e0b100007100010000bf33a5d4d` | `ip:192.168.1.20` |
| `radio_pluto_19f2` | `10400056f695001322002d0010ad1719f2` | `ip:192.168.1.21` |

Preflight verifies those identities and firmware, the exact Leo and
pluto-plus-utils revisions, loaded Python/native libiio identities, native
route/interface/source address, metadata capability, available disk, and
source restoration. The output root is fixed at
`/srv/bulk/leo/qualification/sample-rate-3m`; QNAP, repository, home, symlink,
and broad-root targets fail closed.

### 3 MS/s promotion campaign

The implemented harness performs exactly ten trials; the required
`LEO_PLUTO_RATE_TRIAL_COUNT` value is the literal `10`, not a tunable minimum:

1. Attest the clean committed source revision, pinned dependencies, native
   runtime, host, routes, and fixed production radio pair.
2. Compile the exact committed 60-second canary profile for both fixed radio
   IDs.
3. Run exactly ten simultaneous two-radio, 60-second native-IP captures through
   the complete Leo recorder with K=8, queue=32, production compression, and
   local target storage.
4. Verify every recording, evaluate all ten unique trial checks, and seal the
   deterministic rate-qualification receipt.

Every run must contain exactly 180,000,000 observed and device-span samples
per stream, complete both streams, commit the session, validate every digest,
and report zero gaps, missing samples, overflow, enqueue failures, and terminal
rejections. The receipt requires at least 99% two-radio overlap, queue high-water
no greater than 24/32, and maximum refill service interval no greater than
699,050,666 ns. The separate writer-capacity gate remains at least 72 MB/s.

Failed and incomplete evidence remains beneath `campaigns/`. Only a complete
strict pass is copied atomically and read-only to the canonical accepted path:

```text
/srv/bulk/leo/qualification/sample-rate-3m/accepted/<LEO_REVISION>/contiguous-rate-qualification-receipt-v2.json
```

`<LEO_REVISION>` is the full 40-character target Git SHA. Full deployment
planning and execution accept only that exact non-symlink, read-only path for
the target revision. Operators must pass it through the front door; omitting
the flag fails closed:

```bash
rate_receipt="/srv/bulk/leo/qualification/sample-rate-3m/accepted/$(git rev-parse origin/main)/contiguous-rate-qualification-receipt-v2.json"
./ops deploy --plan --rate-qualification-receipt "$rate_receipt"
sudo ./ops deploy --rate-qualification-receipt "$rate_receipt"
```

The ten recorded minutes remain within the repository's 30-minute RF limit. A
longer production soak is a separate promotion step and needs explicit
authorization consistent with repository policy.

The implemented harness also proves the conservative two-radio RF-time formula
fits within 30 minutes, shares one monotonic deadline across the 3M and 5M
tests, stops admitting phases before the shutdown reserve, and uses the pinned
finite libiio context timeout at every refill. Timeout and cancellation still
flow through both-radio close, exact RX-setting restoration, and post-campaign
TX-safe readback.

The production Ethernet radios and direct-USB controls are separate, explicitly
identified pairs. Safety checks, native-IP canaries, and all durable recorder
trials remain bound to production `.20`/`.21`. The simultaneous USB arm records
the exact `003a`/`3ef2` serials, resolved `usb:` URIs, firmware identities, and
counter metrics; its evidence cannot be relabeled as production-radio evidence.
Where physical USB attachment of `.20`/`.21` is impractical, an operator may
explicitly authorize LAN TOFU with the factory-default password. That exception
uses new private per-radio trust files, exact IIOD and remote gadget serial
attestation, and no user/global SSH trust; USB-anchored enrollment remains the
preferred trust model.

### 5 MS/s characterization

Run at most one 60-second USB diagnostic through the component hardware
benchmark and one 60-second two-radio native-IP diagnostic through Leo. The IP
test passes on truthfulness, not on an expectation of continuity: any gap must
have exact counter-derived evidence, force partial streams/degraded session
state, preserve a verifiable bundle, and suppress automatic analysis.

If bounded burst support is desired, separately repeat the exact proposed
duration on each radio and then simultaneously. Promote only the tested
duration/radio-count envelope, with an all-zero receipt. Do not infer a longer
bound from a shorter pass.

After every authorization and identity variable is populated, invoke the
implemented harness explicitly:

```bash
uv run --extra hardware pytest -ra -s \
  tests/acquisition/test_pluto_rate_modes_hardware.py
```

## Promotion gates

1. **Software implementation — implemented:** the profiles,
   uniform-per-dwell selection, retry affinity, capture-only eligibility,
   strict receipt contract, hardware harness, and cutover verification exist.
   Portable gates must remain green; all 2.5 MS/s identities and scanner
   behavior remain unchanged.
2. **Qualify 3 MS/s transport — pending hardware:** the exact ten-trial
   full-recorder campaign must pass 100% and publish its immutable receipt at
   the canonical accepted target-revision path. This does not enable automatic
   science.
3. **Activate the production pool — pending reviewed cutover:** the operator
   must supply the canonical receipt with
   `./ops deploy --rate-qualification-receipt`. The cutover binds the exact
   ordered 2.5M/3M/5M pool and deployed profile revisions. Ordinary dual-radio
   dwells then select uniformly; 5 MS/s remains segmented and both new rates
   remain `CAPTURE_ONLY`.
4. **Enable science at a new rate:** only through the separately versioned and
   qualified analysis path described above; pool membership is insufficient.
5. **Offer bounded 5 MS/s contiguous bursts:** only after a separate strict
   full-recorder receipt establishes the exact maximum duration and radio
   count.
6. **Offer sustained 5 MS/s contiguous capture:** prohibited by current
   evidence. It requires a new all-zero campaign after a measured transport or
   firmware change; profile configuration alone cannot promote it.

## Recommended delivery slices

1. **Implemented:** profiles, capture-only eligibility,
   profile/admission/adapter/coordinator tests, and uniform selection with
   retry affinity.
2. **Implemented:** strict rate-qualification receipt, exact opt-in hardware
   harness, canonical accepted path, and deployment verifier.
3. **Pending:** bounded ten-trial 3 MS/s campaign and exact production-pool
   cutover using `--rate-qualification-receipt`.
4. Separate scientific-rate ADR and normalized or wideband analysis lane.
5. Optional bounded 5 MS/s burst work only if that use case is required.

Each slice is independently reviewable and preserves truthful recordings even
when a later promotion gate remains red.
