# Matched-bandwidth saved-IQ pilot check

This bounded replay compares each high-rate capture with an anti-aliased 2.5
MS/s version of *the same samples*.  It is a waveform measurement, not an
identity, direction, or phase-calibration result.

## Frozen inputs and split

The inputs are the previously selected source-seeded examples: visit 760 of
`scan-fw-9b88653c7a012fc2` (10 MS/s) and visit 475 of
`scan-fw-894676bdae3d7b2c` (15 MS/s).  Their source hypothesis is each
receiver's existing probe-0, rank-0 GLRT candidate and its acquired CFO.  No
pilot phase, coherence, or result from this replay selects a visit, source,
timing, or CFO branch.

Each 120 ms visit is divided into six whole 20 ms physical groups.  Seed
`20260923` uses Python's `random.sample` to assign training groups `[1, 2, 5]`
and held groups `[0, 3, 4]`; this is a random whole-group split, not a time
split.  The
same group IDs and interior physical samples are used by both arms.  A group is
never filtered with a neighbouring group: anti-aliasing is applied separately
to each group and a fixed 0.25 ms boundary on both sides is discarded.  Thus
the filter cannot carry held IQ into a training statistic.  All six groups and
all failures are recorded.

## Arms and measurements

The prebound acquired-CFO NCO is applied separately to each receiver before
both arms.  This centres the selected pilot before narrow-band filtering; raw
decimation would put the approximately 400 kHz carrier plus an edge tone near
the 2.5 MHz Nyquist boundary.  The full-rate arm then uses the retained 10 or
15 MS/s samples and the narrow arm uses
`scipy.signal.resample_poly(..., down=4 or 6, window=('kaiser', 8.6))`, which
produces 2.5 MS/s output.  Integer decimation factors and the common input
group origin preserve the physical sample time; the template is evaluated at
that physical time rather than at a rounded low-rate epoch.

Both arms fit precisely the same eight published Qin edge-pilot tones, whose
relative span is 1.640625 MHz.  The tone coefficients give an RX1-versus-RX0
pilot vector phase and exact/rolled-template coefficient energy.  A separate
unmodelled broadband cross-RX coherence is reported only as a capture-content
diagnostic.  It must not be treated as a decoded payload or a source-isolated
phase.

A predeclared circular affine phase predictor (one intercept and a principal
slope grid from -25 to +25 Hz) is fit separately for each arm using training groups
only and scored modulo 2π on held groups.  This compares internal phase
repeatability.  The complex cross-vector has ordinary 2π periodicity, and the
20 ms cadence makes slopes separated by 50 Hz indistinguishable.  The reported
slope is only a principal coordinate.  It does not estimate satellite motion.

The result can show whether retaining high-rate bandwidth improves this fixed
known-pilot or raw cross-receiver diagnostic for these two saved dwells.  It
cannot show a generic sample-rate benefit: front-end response, source mixture,
and the unmodelled spectrum differ between captures.

## Execution status

The first execution used a NumPy seeded permutation which happened to place
groups `[0, 1, 2]` in training and `[3, 4, 5]` in held response.  Although the
algorithm was seeded, that realized split is chronological and is not suitable
for the required validation policy.  Its output is retained in the artifact
root.  The later Python seeded-sample split above was run only after the first
output had been inspected.  It is therefore a retrospective development
comparison, not a new held-out result.  No arm, source, timing, or branch was
selected from either outcome.
