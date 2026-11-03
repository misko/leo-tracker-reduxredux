# Joint receiver-pattern and Doppler association for DS11

The user's new direction is to use RX0-only, RX1-only and joint detections to
distinguish satellite candidates, with soft associations, temporal limits and
bounded orbit corrections. This is a viable research direction independently
of obtaining antenna altitude. The earlier altitude impasse does not block
constructing and testing this association model.

## Working geometry and its interpretation

The user confirmed the working RX0-west/RX1-east mapping and nominal opposing
outward tilt in response to the geometry question. Existing metadata describes
10 degrees outward per antenna; the user also mentioned 22 degrees. Do not
silently equate boresight separation with overlap width or a measured gain
pattern. Keep exact separation/beam width as explicit calibration inputs. This
document does not rewrite the historical immutable pose authorities.

For a matched source, RX0-only should favor the west-facing response, RX1-only
the east-facing response, and both the overlap region. Neither observation is
an absolute directional rule. Detectability depends on beam response, source
strength, RF, receiver sensitivity and detection threshold. Both detections
favor near-zenith geometry only to the extent that calibrated beam overlap
lies there. Sidelobes and missed detections retain finite probability.
Beamwidth is a response convention, not a binary visibility boundary; see the
[NTIA antenna models reference](https://www.ntia.gov/files/ntia/publications/antenna_models_report_tm-13-489.pdf).

## New DS11 support measurement

The read-only public tracking port supplies paired 20ms analyzed probes:

| Scan | RX0 only | RX1 only | Both nonempty | Both empty | Unknown/inconsistent |
|---|---:|---:|---:|---:|---:|
| 0 | 344 | 68 | 1499 | 307 | 0 |
| 16 | 70 | 36 | 1985 | 126 | 0 |

Every pair has matching RF, device counter and probe offset; capture and timing
qualification pass. Two tests check all four outcomes and missing/duplicate/
incompatible receiver handling. Full opportunities and source bindings are in
[census.json](census.json). These are any-candidate outcomes, not source-specific
detection events. In particular, both receivers being nonempty does not prove
that both detected one satellite. No new RF, IQ processing or position fitting.

## Proposed model

Use one stationary receiver position per scan. Each possible physical source
has a satellite identity shared across compatible RX/RF tracklets, a presence
state that may turn on/off, and separate receiver/RF nuisance offsets. Keep
multiple association hypotheses rather than hard-labeling tracks first.

Jointly sum over (a) candidate satellite identities, (b) cross-receiver matching
of detections to sources versus clutter, and (c) source presence. The emission
combines Doppler shape with candidate-specific line of sight and the paired
receiver detection pattern. Use the same position and satellite state for all
terms. Include an unmodeled-source/omitted-candidate alternative; a weak bank
must not force confident identification. Preserve independent simultaneous
emitters, including multiple real detections in one probe.

For source j at time t, conditional on common strength a and presence, a simple
starting detector model is p_r = logistic(a + gain_r(LOS_j, RF) - threshold_r).
Conditional receiver detections have four probabilities p0*p1,
p0*(1-p1), (1-p0)*p1 and (1-p0)*(1-p1). Marginalize a shared strength variable
to account for dependence between receivers. Fit receiver/RF sensitivity and
false-detection terms on independent calibration recordings; don't let an
RX0 sensitivity advantage automatically become west-sky evidence. Missing
observation opportunities contribute no non-detection penalty. Include every
qualified analyzed opportunity, not just successful track detections.

The detection-state formula applies to latent source membership, not raw probe
nonemptiness. Cross-RX matching should use temporal overlap, exact RF, frequency
evolution and pilot consistency where available, while marginalizing different
receiver CFOs. Do not demand equal raw CFO across receivers. Do not convert
thresholded GLRT margins into calibrated power or use the same detector statistic
as two independent pieces of evidence.

For temporal limits, use a continuous-time presence transition over actual gaps.
Identity stays constant within a connected physical-source hypothesis; it must
not switch satellites every visit to explain errors. After gaps, permit weak
linkage/new tracks. A short block can propose associations, followed by a joint
scan-level reconciliation. No fixed persistence time is claimed calibrated yet.

For orbit uncertainty, begin with unchanged causal states. Add only a separately
calibrated, finite, shared satellite correction in a later ablation. The same
correction must affect Doppler and LOS across all receiver tracks. Do not add
independent per-track slopes or let correction bounds be chosen from DS11
position error. The recent orbit-revision mixture improved prediction but
worsened geographic results, so its prior is not automatically suitable here.

## What prior experiments establish

- [Joint identity](../joint_identity/README.md) already ties conditional source
  labels across tracks, but adds no independent receiver-pattern likelihood.
  Its small positional effect does not test the proposed observation model.
- [Nominal beam cross-validation](../../2026_09_28_rx_nominal_beam_cv/README.md)
  found reception gains that reversed on later windows. A fixed tilt feature
  alone is therefore not a validated association solution.
- [Explicit presence modeling](../../2026_09_28_rx_presence_geometry/README.md)
  changed the relative ranking of earlier geometry arms. Presence, clutter and
  receiver calibration must be fitted jointly rather than appended to old scores.
- [Paired direction support](../../2026_09_28_rx_paired_direction_support/README.md)
  distinguishes candidate trajectory diversity from duplicate track hypotheses.
  Geometry only helps association when alternative satellites predict different
  receiver behavior. A strong posterior under the old model is not identity truth.

## Recommended bounded iteration

1. Build source-specific paired matching hypotheses for the two audited DS11
   scans, preserving uncertain matches and all empty opportunities. At fixed
   original positions, report how much candidate LOS/receiver-pattern predictions
   differ. If rival candidates predict effectively the same pattern, do not
   inflate association confidence.
2. Calibrate the four-state detector model on disjoint existing recordings with
   compatible hardware and RF coverage. Test geometry against a receiver/RF-only
   model, RX swap and candidate-geometry permutation. Retain absent/clutter states
   and held whole sources/time blocks. No selection by DS11 reference error.
3. Only then compare full single-scan positioning with Doppler alone, Doppler
   plus receiver evidence, and finally bounded shared orbit uncertainty. Freeze
   priors and selection rules before scoring geographic errors. Report candidate
   ambiguity, failed outputs, median/P90 and paired position changes. Confirm on
   additional recordings; interpolation log-score gains alone are insufficient.

This design and support census are complete. Cross-receiver source matching,
detector calibration and the new joint solver are not implemented or validated
by this artifact. No association or position improvement is claimed yet.
