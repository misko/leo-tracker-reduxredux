# Shared satellite phase and small hardware drift: continuation checkpoint

The DS22 / DSX01 association and <0.5-km positioning goal remains active.
Eight blind phase experiments have completed. No related search, resume, panel
or consolidation process remains running. Original search sources were verified
and archived before adding configurable small-drift settings.

Full-137 DS22 population and fixed-site comparison remain authoritative in
../2026_10_17_ds22_physical_model_revision/. This report is two pilot cases only.

## Completed results

- Shared phase increases frequency-compatible coverage but worsens blind position:
  DS22-00113.615km vs zero-phase11.698/11.760; DSX01-S0113.434km vs5.734/5.616
  (c0/fitted-c). More compatible points do not establish correct identities.
- All8 blind fits,16 original diagnostic and8 tight-drift diagnostic fits complete.
  All32 consolidation arms lose zero admitted point IDs or candidate identities.
- Original DSX shared searches timed out after600s during finalist evaluation.
  search_resumed/ replayed verified cached discovery scores with identical search
  path/budget, no GPS/diagnostic initializer. Original interrupted artifacts kept.
- Drift is configurable end-to-end: --drift-sigma-hz-s 0.5 --drift-bound-hz-s 1.
  Historical defaults2/5 remain for old policies. Bound0 supported. Initial
  states and no-update retained fits also obey bounds; invalid policies fail early.
- Four independent scan-local hardware offsets/slopes: RX1low/high,RX2low/high.
  Their differences give cross-RX/band contrasts including an interaction.
  Only measured-curved original fragments calibrate. Linear tracks can associate.
- Tight phase at supplied GPS admits1383/1150 DS22 and1975/1975 DSX points(c0/fc).
  Both wrong blind endpoints still score better. Several ±1-Hz/s bounds active:
  these are uncertain estimates, not established physical LNB drift.
-23 targeted tests passed: four-group independence, drift bound on no-update fits,
  linear exclusion, dense-Schur parity, geometry, panel mapping, public estimator.
  Ruff passed on changed tools/tests. No golden fixture changes.
- Conditional information has kilometre-scale weak axes and conditions on labels
  and priors. Phase/zero admitted sets differ; a same-anchor sensitivity ablation
  is still needed before attributing information loss to nuisance freedom alone.

## New measurement evidence and next experiment

Stored pair-autocorrelation GLRT CFO selects a512pointFFT bin at4.4us correlation
sampling:443.892Hz spacing. Fractional tracking refines epoch, not continuous CFO.
Use the existing public estimate_edge_pilot_frame_cfo estimator, not a new demodulator.

tools/qualify_track_frame_cfo.py evaluated two points (20/80percent) from the two
longest measured-curved tracks per RX/band:16points/case, noGPS/labels for selection.
Read-only existing IQ/public FastScanStore/FastSegmentSource:14/16DS22 and15/16DSX
qualified; median conditional estimator uncertainties16.6/18.4Hz, not independently
calibrated. Artifacts copied to pilot_cfo_panel/; source/tests archived.
Original observations, times, detector decisions and positioning fits unchanged.

Legacy DSX graph times differ from source counter midpoints by up to0.503ms.
Matching requires unique receiver/channel support within0.51ms AND exact modulo-P
reproduction of an originally gated CFO peak; actual differences remain per point.
The earlier strict time-key join failed before IQ read/output; fixed and both
panels rerun under one frozen source. Earlier temp outputs not used in report.

Next: extend response-only selection to complete tracks, retain unsupported
measurements explicitly and original point IDs/denominators, evaluate continuous
pilot residuals, then matched c0/fc localization. Verify accuracy before scaling
to all137DS22 or claiming goal. A stationary multi-scan position fit may help,
but must retain independent hardware per scan and declare stationarity assumption;
optional scope question unanswered.

No RF collection, QNAP writes, reference-repo runtime dependency, production
promotion or new remote push. README.md, figures,CSV tables and seal.json hold
the reviewable result; broader goal stays active.
