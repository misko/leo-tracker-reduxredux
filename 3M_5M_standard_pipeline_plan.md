# 2.5/3/5 MS/s Standard Pipeline PNG Completion Plan

Date: 2026-08-26

Status: proposed for implementation

Branch: `codex/3m-5m-sample-modes`

Baseline: `73bd6df2ef06190007c62327147e7c4dbf864d31`

## Outcome

Complete one native-rate Standard pipeline for new 2.5, 3, and 5 MS/s
Recording V3 captures. The three rates must run the same production scientific
kernels, the same gap-aware projection code, and the same PNG renderers at the
recording's exact input sample rate. No IQ resampler, decimator, interpolator,
or rate-specific scientific branch is permitted.

At completion, the browser must show the complete Standard PNG inventory for
all three rates:

- eleven PNGs for each receiver path;
- the five common PNGs for each radio;
- the five common PNGs for the paired-radio subject; and
- the same artifact names, ordering, captions, and scope rules at 2.5, 3, and
  5 MS/s.

For the production two-radio, dual-receiver topology this is 59 PNGs per run:

```text
4 receiver paths * 11 PNGs = 44
2 radios         *  5 PNGs = 10
1 paired subject *  5 PNGs =  5
                                --
                                59
```

A gap does not remove an expected artifact. A gapped run publishes the same
inventory with truthful `PARTIAL_COVERAGE` or `INSUFFICIENT_DATA` content,
blank or interrupted plot regions, and explicit coverage annotations.

## Meaning of "the identical pipeline"

The identity requirement applies to scientific behavior and orchestration:

1. One `standard-native-v1` graph admits the reviewed 2.5, 3, and 5 MS/s
   device-axis profiles.
2. One production configuration builder resolves the small rate-derived
   geometry from the bound input rate before its digest is calculated.
3. The existing production pilot, Hough, de-alias/replay, final-trajectory,
   QAM, Kalman, pilot-Doppler, and full-capture GLRT kernels run directly on
   native-rate IQ.
4. One segment-aware presentation adapter feeds the existing Standard plot
   semantics for all three rates.
5. A lossless recording is the one-segment case. A gapped recording runs the
   same kernels only on wholly valid windows and resets all state at every
   continuity boundary.

It does not mean mutating or pretending to reuse the historical Standard-v2
wire contracts. Published contract majors remain immutable. Historical
Standard-v2 products remain readable and provide regression oracles; new
device-axis captures use additive native contracts that preserve validity and
segment authority.

Converting sample indexes to seconds, FFT bins to hertz, or plot values to
pixels is presentation, not IQ downsampling. No renderer may change, filter,
decimate, resample, or reconstruct the underlying IQ.

## Non-negotiable invariants

- Literal zero fill preserves the logical device-time axis but never becomes
  observed scientific evidence.
- For the same rate, duration, and receiver layout, gapped and lossless
  recordings have the same logical CI16 byte length. Verification must prove
  literal zero bytes at every invalid device-axis interval.
- No FFT, pilot, symbol, frame, GLRT, QAM, CFO, Doppler, trajectory, Hough, or
  Kalman operation crosses a continuity boundary.
- Stateful algorithms reset for every authoritative segment.
- Power, quality, and QAM use valid-sample sufficient statistics, never simple
  averages of already-derived ratios or dB values.
- Waterfalls retain the fixed global time/frequency axes. Missing support is
  rendered blank or unavailable, not as zero power.
- The WebUI does not expose a numerical "waterfall cell validity" table.
  Validity remains an internal rendering and provenance concern.
- Paired rendering uses the exact intersection of the radios' valid UTC
  intervals. Segment ordinals from different radios are never assumed to
  match.
- PNG jobs consume sealed, digest-verified predecessor products. They do not
  reread IQ and do not render on demand in the API process.
- Every published PNG binds its exact source-product digests and subject
  identity.
- Frozen Standard-v2 registry, products, presentation bytes, and historical
  Current behavior remain unchanged.

## Required PNG inventory

`Path` means each of the four receiver paths. `Radio` means each of the two
radio subjects. `Paired` means the single paired-radio subject.

| # | PNG artifact | Required scopes | Sealed native source | Addition required |
|---|---|---|---|---|
| 1 | Waterfall | Path, Radio, Paired | Native numerical waterfall V3 containing the exact numerical waterfall V2 grid | Reuse the current renderer through a 1/2/4-path source adapter. Publish path and radio versions and complete paired rendering. Preserve global axes and render missing support blank. |
| 2 | Pilot methods | Path, Radio, Paired | Stateful V2 detections, method scores, primary-QAM evidence, and conditioned replay | Adapt typed segment-local detections to the existing renderer, translate to global time, and insert hard breaks between segments. |
| 3 | Raw CFO trajectories | Path, Radio, Paired | Detections, raw residual-Hough bank, representatives, observations, and alias authority | Rebuild the existing presentation table from sealed rows and render each segment independently. Never refit or join tracks across gaps. |
| 4 | De-aliased CFO trajectories | Path, Radio, Paired | Exact de-aliased bank and canonical observations per segment | Reuse the current plot semantics through a typed segment adapter. Offset times globally without changing model coefficients or associating branches across segments. |
| 5 | Final CFO trajectories | Path, Radio, Paired | Exact final trajectory bank and terminal path-report tracks | Apply the existing pure final-table projection per segment and render disconnected global-time traces. |
| 6 | Alternate-Hough CFO | Path only | Existing native alternate bank and PNG projection | Retain the IQ-free projection and add legacy visual parity: raw candidate scatter and visible alias lifts from sealed evidence. Do not rerun Hough. |
| 7 | Trajectory-conditioned replay accounting | Path only | Detections, representatives, conditioned replay, and alias map | Run the existing accounting builder independently per segment, seal an additive segment-aware V3 accounting product, combine only integer counts/sufficient statistics, and render it. This is the only missing derived product; it needs no IQ. |
| 8 | Full-capture 20 ms GLRT | Path only | Native full-capture GLRT V1 global opportunities and per-segment Hough/rate results | Add a typed renderer adapter. Show excluded opportunities and draw every segment fit independently using thresholds from the verified release configuration. |
| 9 | Pilot Doppler qualification | Path only | Exact pilot-Doppler V2 evidence nested in each analyzed segment | Reuse the current renderer with segment-to-global time translation and reset markers. Aggregate additive support/count fields only; rates, coherence, RMS, phase, and fit values remain segment-local and are never averaged. |
| 10 | Pilot carrier tracking | Path only | Pilot-Doppler, Kalman, and final-bank evidence per segment | Reuse the current renderer, plot every segment independently, and make no phase or state-continuity claim across gaps. |
| 11 | Pilot segment-rate comparison | Path only | Local, Kalman, and frozen rate evidence per segment | Reuse the current renderer with global interval offsets. Keep every rate line confined to its segment and never average segment rates into a synthetic track. |

Rows 1-5 have the same Path/Radio/Paired scope coverage as the frozen 2.5 MS/s
Standard presentation. Rows 6-11 are receiver-path diagnostics only.

## Current implementation boundary

The native Standard graph already:

- admits exact reviewed 2.5, 3, and 5 MS/s profiles;
- runs the production rate-resolved configuration and scientific kernels;
- seals path quality, power, numerical waterfall, probe schedule, stateful V2,
  full-capture GLRT V1, and path report V3 products;
- projects and publishes the alternate-Hough JSON and PNG without IQ; and
- publishes the paired waterfall PNG.

The current executable graph publishes only five PNGs for a two-radio,
dual-receiver run: four path alternate-Hough PNGs and one paired waterfall.
The remaining scientific inputs are already sealed. The delivery gap is
primarily typed projection, rendering, registry output closure, API exposure,
and WebUI gallery support.

Trajectory-conditioned accounting is the sole missing derived scientific
document. It is deterministically reconstructable from sealed stateful rows
and the verified production configuration; it does not require an IQ read or a
new detector.

## Target architecture

### 1. Shared segment-aware plot source

Add one internal typed projection layer used by every native PNG renderer. It
must carry:

- exact source and subject identity;
- native `sample_rate_hz` and timing authority;
- continuity segment ID and device-axis bounds;
- segment-local and global time conversion;
- the exact predecessor artifact digests;
- valid UTC intervals and coverage; and
- an explicit gap/reset inventory.

The projection layer must produce only renderer input values. It must not read
IQ, invoke a detector, alter scientific estimates, interpolate missing data,
or flatten segment identities.

### 2. Segment-aware accounting product

Add the already-reserved native trajectory-conditioned-accounting V3 product.
Build it from the sealed stateful V2 rows with the existing Standard accounting
algorithm once per continuity segment. Its aggregate layer sums transition and
support counts. Ratios are derived once from the summed sufficient statistics.

Do not add fields to a published stateful contract and do not reinterpret the
historical accounting V2 major.

### 3. Preserve the 12-job topology

Keep the existing twelve jobs and four raw-IQ reads:

```text
4 * path-standard-native             IQ access: receiver path
4 * path projection/presentation     IQ access: none
2 * radio-scientific-report-native   IQ access: none
1 * paired-scientific-report-native  IQ access: none
1 * paired-presentation-native       IQ access: none
```

Required stage changes:

1. `path-standard-native` remains the only IQ-reading stage and continues to
   seal its seven canonical path-science products atomically.
2. Broaden the existing IQ-free `path-alternate-tracks-native` projection into
   the complete path presentation stage. It consumes the exact sealed path
   products, derives and seals accounting V3 from the canonical serialized,
   digest-bound stateful V2 document, and emits the alternate bank plus all
   eleven path PNGs. Accounting is an IQ-free projection-stage output, not a
   predecessor of its stateful source. Retain or
   rename the stage only through a new pipeline definition and bumped
   algorithm/configuration identities.
3. `radio-scientific-report-native` continues consuming the two exact path
   subjects for its radio and additionally emits rows 1-5.
4. `paired-presentation-native` emits rows 1-5. It consumes the paired report
   as the authoritative common-valid-UTC intersection as well as the sealed
   child path plot sources. This adds one dependency edge but no job or IQ
   read.

With the recommended persisted accounting document, the expected catalog
inventory for a two-radio, dual-receiver run is:

| Stage family | Per-job outputs | Jobs | Products |
|---|---:|---:|---:|
| Path science | 7 | 4 | 28 |
| Path projection | 13 | 4 | 52 |
| Radio report and presentation | 6 | 2 | 12 |
| Paired report | 1 | 1 | 1 |
| Paired presentation | 5 | 1 | 5 |
| **Total** |  | **12** | **98** |

The 98 products comprise 59 PNGs and 39 scientific, lineage, or authority
documents. The complete browser artifact inventory introduced below is an
API/read-model contract, not another persisted catalog product.

### 4. Radio and paired semantics

Radio and paired renderers must consume exact child products rather than infer
detailed plot series from terminal summary counts.

- Radio plots contain the two receiver-path series for that radio.
- Paired plots contain the four receiver-path series only over the exact
  paired valid-UTC support.
- Labels retain radio, receiver, segment, and trajectory identity.
- Power/QAM summaries merge energy and count sufficient statistics.
- Trajectory and Kalman models remain individual reset-local models; reducers
  never average coefficients or bridge gaps.

### 5. Additive API and WebUI delivery

Do not widen a published V3 artifact-name literal or its two-artifact limit in
place. Add an immutable API/read-model presentation contract version that
advertises the complete closed artifact inventory. This is not an additional
catalog product and therefore does not change the 98-product run inventory.

The API must:

- return only cataloged PNG artifacts bound to the Current run authority;
- support GET and HEAD for every valid artifact name;
- reject wrong-scope, duplicate, missing, corrupt-digest, and foreign-run
  artifacts;
- never render from scientific JSON during a request; and
- preserve frozen Standard-v2 routes and response schemas.

The WebUI must:

- show eleven ordered images for a receiver path;
- show five ordered images for a radio or paired subject;
- use the same labels and ordering at 2.5, 3, and 5 MS/s;
- show partial-coverage or insufficient-data captions without hiding the PNG;
- render missing waterfall regions blank inside the PNG; and
- contain no numerical waterfall-cell validity table or validity-cell fetch.

## Implementation phases

### Phase 0: Freeze inputs and compatibility oracles

- Record the exact current Standard-v2 renderer inputs, output identities, and
  representative PNG digests without changing their golden fixtures.
- Freeze the native path/report/stateful/GLRT source contracts used by every
  adapter.
- Add a closed list of the 11 Path and five Radio/Paired artifact names and
  their browser order.
- Confirm all new public schemas use additive majors.

Exit gate: contract and registry tests prove the frozen Standard-v2 product
inventory and bytes are unchanged.

### Phase 1: Pure projection and accounting

- Implement the storage-neutral segment-aware plot-source adapter.
- Implement per-segment trajectory-conditioned accounting V3.
- Add direct adapters for waterfall, pilot methods, raw/de-aliased/final CFO,
  full-capture GLRT, and pilot-Doppler views.
- Extend alternate-Hough rendering to visual parity without refitting.

Exit gate: pure component tests pass for continuous and adversarial gapped
fixtures at all three rates, and a reader that raises on any IQ access is never
touched.

### Phase 2: Analyzer registry and lineage

- Add the accounting document to the atomic IQ-free path-projection batch.
- Expand the path projection stage to all eleven PNGs.
- Add the five radio and five paired PNG outputs.
- Bind every PNG to exact predecessor job/product digests.
- Bump only native algorithm, configuration, graph, and pipeline-definition
  identities affected by the new output closure.

Exit gate: the compiled topology remains 12 jobs, only four jobs have IQ
authority, the paired-report presentation dependency closes the graph at
exactly 15 edges, every declared output is published atomically, and a
complete two-radio run seals exactly 98 products including 59 PNGs from 32
declared stage-output specs.

### Phase 3: Presentation API and browser

- Add the additive complete artifact-inventory presentation contract.
- Load and verify stateful, GLRT, accounting, terminal, and PNG lineage through
  the native Current projector.
- Expose all artifact routes with strict subject-scope validation.
- Generalize the native PNG gallery to the 11/5/5 inventory.
- Remove or keep absent every waterfall-cell validity-table surface.

Exit gate: API and browser tests load every expected image and no unexpected
artifact, with the same names/order for all three rates.

### Phase 4: Scientific and corpus verification

Run the same renderer and graph tests at exact 2.5, 3, and 5 MS/s. Required
protected recordings are:

- 2.5 MS/s: `cap-20260825T212100-f5e627722c6c`;
- 3 MS/s: `cap-20260825T213600-dd352bd0e4fc`;
- full-span gapped 5 MS/s: `cap-20260825T214800-edc045ea9a07`; and
- truncated 5 MS/s refusal control: `cap-20260825T211500-642ccf40a8c1`.

The accepted corpus runs must execute the complete native graph and renderer
inventory, not only admission or a single detector probe. Repeat execution
must produce identical typed product and PNG digests under the same release.

Exit gate: all three accepted rates produce the complete expected inventory;
the truncated control fails before run creation/publication.

### Phase 5: Release and deployed vertical

- Add all renderer, PostgreSQL, API, browser, and exact-corpus nodes to the
  canonical release qualification inventory.
- Build, stage, and validate one immutable release.
- Verify schema head, resource capacity, release-tree authority, workers,
  storage, RAID, and capture authority without rebooting.
- Deploy only after the full software and protected-corpus gates pass.

Exit gate: the sealed release receipt proves every required test command and
the staged WebUI build includes the complete native gallery.

### Phase 6: Bounded production canaries

No reboot is permitted. Do not touch local USB radios. If new RF is required,
use only `192.168.1.20` and `192.168.1.21` through
`/home/mouse9911/gits/pluto-plus-utils`. Any required change to that repository
must be reported to the user before modification and published as an issue.

Keep durable acquisition paused. Use the protected corpus and an existing
production recording for the deployed 2.5 MS/s proof; do not collect new
2.5 MS/s RF merely for this PNG change. Execute sequential, isolated 60-second
device-axis canaries at 3 and 5 MS/s, re-pausing and draining processing
between rates. The two-rate campaign must remain comfortably within the
30-minute RF authorization bound.

For every canary:

1. verify the exact capture profile and release authority;
2. capture one dual-radio, dual-receiver dwell;
3. require manifest, timeline, gap-map, validity, and logical-count closure;
4. run the complete native Standard graph;
5. require the complete 98-product/59-PNG inventory;
6. verify the Current pointer and native presentation authority;
7. GET and HEAD every expected PNG through the production API;
8. open each subject in the production browser and require every image to have
   nonzero natural dimensions; and
9. pause again before selecting the next rate.

The 5 MS/s run may truthfully finish as `PARTIAL_COVERAGE` when the capture has
counter-proven gaps. That status is acceptable only if every missing interval
is closed by the validity authority and every expected PNG still publishes
without a line, fit, FFT, or state transition crossing a gap.

## Test matrix

### Renderer and scientific invariants

- Parameterize every renderer over 2.5, 3, and 5 MS/s.
- Assert native input sample rate is preserved in every source binding and
  physical axis.
- Assert there is no resampler/decimator/interpolator stage, import, product,
  or lineage edge.
- Test one-sample, FFT-sized, probe-sized, refill-sized, initial, internal,
  terminal, and zero-length reset boundaries.
- Prove invalid zero fill cannot change power, quality, QAM, detections, or
  rendered scientific values.
- Assert equal-rate/equal-duration gapped and lossless recordings have the
  same logical CI16 byte length, and verify zero-fill bytes at exact gap
  offsets.
- Prove no matplotlib primitive connects points with different segment IDs.
- Prove waterfall gaps become blank/NaN regions and never dark measured RF.
- Prove empty but valid scientific results publish deterministic
  `NO_RESULT`/`INSUFFICIENT_DATA` placeholder PNGs.
- Require deterministic PNG bytes for the same sealed sources, configuration,
  and renderer version.

### Registry, catalog, and processing

- Exact stage input/output inventories and algorithm/configuration identities.
- Exactly 12 jobs, 15 dependency edges, and four receiver-path IQ authorities.
- Exactly 32 declared stage-output specs.
- Exactly 98 products and 59 PNGs for the production 2x2 topology.
- Exact product dependencies from every PNG to the sealed source products.
- Atomic failure: renderer error or `BaseException` publishes no partial
  product batch and does not replace the prior Current run.
- Wrong rate, source, segment inventory, digest, subject, or release fails
  closed.
- Frozen Standard-v2 and historical V2 evidence behavior remain unchanged.

### API and browser

- Distinguish the 11/5/5 catalog PNG identities from public route aliases; an
  alias must resolve to the same catalog artifact and must not create a
  duplicate product.
- GET and HEAD the three plot-view routes (waterfall, GLRT64/pilot methods, and
  raw-CFO trajectory) at every supported scope.
- GET and HEAD all nine named Path routes: raw, de-aliased, final, alternate,
  trajectory accounting, pilot Doppler, carrier tracking, segment rates, and
  full-capture GLRT.
- GET and HEAD the three applicable named Radio/Paired routes: raw,
  de-aliased, and final CFO.
- Wrong-scope artifact names return a typed not-found response.
- Corrupt, duplicate, unregistered, or foreign-run artifacts are rejected.
- Every returned body has `image/png`, a valid PNG signature, and the cataloged
  digest.
- Browser gallery ordering and labels are identical across rates.
- Every image reports `naturalWidth > 0` and `naturalHeight > 0` in Chromium.
- No waterfall validity table, cell endpoint, or cell-level network request is
  present.

## Rollback

- All public changes are additive; do not rewrite published contracts or
  existing artifacts.
- A failed expanded run cannot replace the prior Current pointer.
- Before deployment, rollback is simply omission of the new pipeline
  definition from the release.
- After deployment, stop acquisition and workers, restore the prior immutable
  release selectors, validate them, and restart the prior services. No reboot
  or destructive catalog/storage operation is needed.
- Preserve all failed run, capture, manifest, gap, and product evidence for
  diagnosis.

## Definition of done

The work is complete only when every condition below is true.

### Pipeline identity

- [ ] New 2.5, 3, and 5 MS/s device-axis captures use the same reviewed
  Standard-native graph and production kernel configuration.
- [ ] All science runs at the exact captured sample rate; no IQ downsampling or
  resampling exists anywhere in the graph or product lineage.
- [ ] Lossless and gapped recordings use the same code path, with the lossless
  recording represented as one valid segment.
- [ ] Frozen Standard-v2 contracts, products, golden fixtures, and historical
  browser behavior are unchanged.

### PNG completeness for each rate

For each of 2.5, 3, and 5 MS/s:

- [ ] Every one of four receiver paths has exactly eleven registered PNGs:
  waterfall, pilot methods, raw CFO, de-aliased CFO, final CFO,
  alternate-Hough CFO, trajectory-conditioned accounting, full-capture 20 ms
  GLRT, pilot Doppler qualification, pilot carrier tracking, and pilot
  segment-rate comparison.
- [ ] Every one of two radio subjects has exactly five registered PNGs:
  waterfall, pilot methods, raw CFO, de-aliased CFO, and final CFO.
- [ ] The paired subject has exactly the same five registered PNGs.
- [ ] The run therefore contains exactly 59 PNGs, with no missing, duplicate,
  wrong-scope, unregistered, or corrupt artifact.
- [ ] Every PNG is generated from sealed predecessor products, has exact
  lineage, deterministic bytes, and a valid PNG signature.
- [ ] `PARTIAL_COVERAGE`, `NO_RESULT`, and `INSUFFICIENT_DATA` subjects retain
  the complete artifact inventory with truthful captions/placeholders.

### Gap truthfulness

- [ ] No rendered FFT, probe, frame, GLRT result, trajectory, phase trace,
  Doppler fit, or Kalman state crosses a gap.
- [ ] Stateful traces visibly stop and restart at continuity boundaries.
- [ ] Power, quality, and QAM summaries use valid samples and merge sufficient
  statistics.
- [ ] Waterfall time axes remain fixed; missing cells are blank and are not
  presented as measured zero power.
- [ ] Equal-rate/equal-duration gapped and lossless captures have the same
  logical CI16 byte length, with verified physical zeros at invalid offsets.
- [ ] Paired plots use only the exact common-valid UTC intersection.
- [ ] The WebUI contains no waterfall-cell validity table.

### End-to-end publication

- [ ] Protected 2.5, 3, and gapped 5 MS/s corpus recordings complete the full
  graph twice with identical typed and PNG product digests.
- [ ] The truncated 5 MS/s control is rejected before publication.
- [ ] Real PostgreSQL verifies 12 jobs, 98 total products, 59 PNGs, exact
  dependency closure, atomic sealing, and safe Current promotion.
- [ ] Production API GET/HEAD succeeds through every view and named route for
  every expected PNG, route aliases resolve to one catalog artifact, and every
  invalid scope or digest is refused.
- [ ] The production browser displays all eleven Path and five Radio/Paired
  PNGs, in the same order, for 2.5, 3, and 5 MS/s.
- [ ] Browser-loaded images have nonzero dimensions and no artifact request
  fails.
- [ ] Canonical release qualification, staged validation, WebUI qualification,
  and deployment cutover checks all pass at the exact release SHA.
- [ ] Deployed 2.5 MS/s protected-corpus/existing-recording proof and sequential
  3 and 5 MS/s canaries on only `192.168.1.20`/`192.168.1.21` complete without
  reboot, local-radio access, overlapping capture/analysis, or lost evidence.
- [ ] Acquisition is left paused after the bounded canaries unless the user
  separately authorizes continuous acquisition.

Only after this checklist is closed may the 2.5/3/5 MS/s Standard PNG work be
called complete.
