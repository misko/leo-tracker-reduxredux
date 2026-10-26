# Synthetic measurement continuity, frozen before new detector outcomes

This is a pilot-only synthetic mechanism test in the identical deployed environment
and unchanged public `production_glrt` port bound by the previous IQ control.
There is no recorded IQ, provider/capture attestation, new RF, satellite, GPS or
position inference. The actual graph constructor is `graph_tracklets.fit_lane`,
called by the existing `evaluate_ds22_merged_tracks.graph_tracks` numerical adapter.
Its selected DS24 configuration is hash-bound, unchanged: noise150Hz, association3,
minimum8points/6seconds, maximum degree4 and slope8000Hz/s. Source chronology here
is a declared synthetic one-second cadence, not an original acquisition schedule.

Six closure windows compare three laws at integer epoch127, one source100kHz at
amplitude1000 or coincident100/103kHz sources at1000/600, phases .3/−.8rad.
`sampled_deployed` copies the deployed complex64 frame into anchors
epoch+round(k*10MHz/750), including previous-frame support. `sampled_right` independently
uses the previous continuous generator evaluated on the integral frame grid at the
same rounded anchors. These differ at the known68 symbol-boundary samples. `continuous`
uses that generator's original exact fractional frame period. All use the same
seed20261026 complex Gaussian noise, independent receivers, complex RMS300ADC.
Noisy int16 quantization rounds once and clipping must be zero. Template-sampled
closure is an inverse-model/discretization control, not physical waveform validation.
In particular it does not assert that fractional interpolation is a physical law.
The detector executes with the immutable historical deployed source and its
`/opt/leo-fast-auto/20261010-r1/venv/bin/python`; saved dictionaries are the only
port to a separate repository-process graph. The deployed package omits the graph
component. Package paths are not mixed, and detector identity is checked before
and after its calls. The template bytes used by independent waveform construction
must equal deployed bytes. Initial preparation guarded a wrong repository detector
identity and a missing graph import in the lean deployed tree before any detector
call; both logs and1.639935032worker-seconds are retained/deducted.

Two base sequences use coincident epochs127/127 or separated epochs127/811.
Each is evaluated under `sampled_deployed` and `continuous` at t=0,…,15seconds,
20ms windows,10MHz,two receivers. There are64 sequence calls plus6 closure calls.
Source A CFO=100000+200T Hz and B=103000−200T Hz, evaluated at global T=t+n/fs;
carrier phase integrates that global trajectory with initial phases .3 and−.8rad.
At each visit, amplitudes1000−400t/15 and600+400t/15 are constant during that20ms
window; this is a snapshot amplitude schedule, not a continuously varying envelope.
Frame phase is global: integer-second spacing spans exactly750 frames. Sampled
arms use per-frame rounding, not a fixed13333-sample frame repetition.
The sequence noise child is `SeedSequence([2026102801,visit])`; the exact same draw
is reused across both laws and both epoch conditions. No rerolls or source-dependent
noise. The two receiver noise streams are independent.

Every exported detector peak is persisted. Graph input uses the same complete
fractional-candidate port as deployed tracking, gate≥.025, then maximum fractional
margin, tie smaller rank. No truth chooses a peak. Empty/no-gate windows remain
misses. The synthetic row adapter copies this policy because `public_tracking_points`
requires actual qualified UTC/capture authority, which these synthetic windows lack.
It binds exact synthetic visit/receiver IDs and midpoint times. It does not create
fake capture authority. The actual graph numerical component receives those rows.
The stage-ablation graph uses the SAME selected rank/ID/margin/time, substituting
its `acquired_cfo_hz` before the GLRT residual; it is a prototype diagnostic only.
No all-peak graph or production refinement change is inferred from it.

Response-only final/acquired graph artifacts are written and hash-bound before
source-truth comparisons. Oracle true-CFO per-source lanes use all16 visits with
known source ownership as a separate upper-control, not the actual candidate pool.
Both truth CFO errors (alias-circular), epoch distances, acquired and fractional
residual stages are reported for every complete peak and selected row. A selected
point is labelled A/B only within450Hz of exactly one source at the window midpoint;
within both is `ambiguous`, within neither is `unmatched`. This unchanged graph
association radius is a descriptive evaluation convention, not source validation.
Mixed tracks count A and B labels among their IDs, retain ambiguous/unmatched and
all residual-quality flags. Mixed labels do not prove that the detector measured
one of the two sources: interference may produce neither. Candidate coverage per
source additionally reports joint CFO≤450Hz and epoch≤3samples, with simultaneous
matches ambiguous. No source is backfilled. Graph ownership/assigned IDs are unique.

Preparation reproduces the known68-boundary mismatch, checks code/environment
identity, and sends archived detector output through the actual row/graph input
port. Owned tests cover paired streams, frame anchors/global phase, gates, ties,
empty probes, native row IDs, graph ownership and ambiguous/unmatched diagnostics.
No new detector result is obtained before protocol hashes and B preflight.

At most600 cumulative numerical worker-seconds including preparation/tests/imports;
one numerical worker, BLAS/OMP/MKL1, each detector call≤20seconds and total remaining
deadline unchanged. All70 slots and four graph outputs retained, including failures,
no retry/rescue/parameter changes or extra scientific campaign. Live stdout is
outside measurement/. Source, authority files/config, preparation and input bindings
freeze in protocol.json; B exact preflight precedes one run. Terminal seal precedes
saved-output reporting and independent audit. A failure to reproduce the actual
graph contract stops the experiment rather than substituting another graph.
