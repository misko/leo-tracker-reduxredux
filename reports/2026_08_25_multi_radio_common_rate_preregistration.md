# Preregistration: multi-radio common Doppler rate with free path offsets

## Outcome of the response-blind freeze

This document freezes four bounded, previously opened **POST-FIX** episodes for
the multi-radio experiment before any new raw-IQ frame response is evaluated.
It is a preregistration, not a result. The experiment will ask whether one
RF-normalized linear CFO rate, with a separate constant intercept for every
receiver path, predicts held-out odd-Qin measurements as well as independently
fitting a rate on every path.

The exact machine authority is
[`multi-radio-common-rate-protocol-v1.json`](../config/analysis/multi-radio-common-rate-protocol-v1.json).
It contains all 15 receiver-path bindings, source epochs, aliases, absolute UTC
intersections, nominal RF frequencies, sealed product URIs, and SHA-256
digests. The loader rejects unlisted captures, substitutions, digest drift,
path-identity drift, model expansion, or a path that no longer spans the exact
frozen episode.

At this freeze:

- no new raw-IQ frame profile from these episodes has been read or scored by
  this experiment;
- no odd-Qin response has been inspected;
- all four captures remain pending, including any that later fail support;
- no capture from the protocol-unopened `holdout_foundation` role is present;
- no newer or dynamically discovered capture can enter the run.

## Why these are valid inputs

The parent [dataset policy](2026_08_25_doppler_experiment_dataset_policy.md)
grants exactly these four captures to the `multi_radio` development role. The
[24-hour retrospective](2026_08_25_post_refill_24h_retrospective/README.md)
proved that every stream is counter-authoritative and gap-free: the continuous
recording/refill fix was already operating, device counters span every requested
sample, and there are no reported gaps, missing samples, overflows, enqueue
failures, or terminal rejections. These are therefore **after-fix** data.

The retrospective also published a deterministic simultaneous-path screen.
This freeze takes its exact `screen_path_ids` and `screen_branch_ids`; it does
not rerank paths. Each branch interval is converted from stream-relative time
to absolute UTC with that stream's device-counter-anchored first-sample
estimate. The full intervals are intersected, then the centered 1.500000000 s
subinterval is retained with integer-nanosecond arithmetic.

| capture | full overlap (s) | frozen UTC ns | paths | band relationship |
|---|---:|---:|---:|---|
| `065355` | 14.863928 | `1787640863824860175–1787640865324860175` | 4 | same-band |
| `103607` | 8.700000 | `1787654223218803122–1787654224718803122` | 3 | cross-band |
| `130425` | 9.825000 | `1787663118549042803–1787663120049042803` | 4 | cross-band |
| `150802` | 2.975000 | `1787670489742627359–1787670491242627359` | 4 | cross-band |

The full-overlap column is the already-published screen result. The UTC column
is the new bounded analysis episode, not the full branch duration.

## Exact path and source-epoch freeze

The selected final-bank alias is fixed before local frame analysis. Among the
already-published automatic-correction trajectories for the selected branch,
the rule maximizes the committed median corrected margin, then minimizes
absolute alias index and alias index. Near the episode midpoint, the frozen raw
source is the exact branch-bound GLRT64 observation within 75 ms that maximizes
committed margin, then exact score and midpoint proximity.

| capture | path | edge | nominal sky GHz | local interval (s) | alias | source sample + epoch |
|---|---|---|---:|---:|---:|---:|
| `065355` | `stream-0/5d4d/RX1` | upper | 11.690312500 | 24.993036053–26.493036053 | -1 | `64437500 + 1331` |
| `065355` | `stream-1/19f2/RX1` | upper | 11.690312500 | 25.131963946–26.631963946 | -1 | `64812500 + 166` |
| `065355` | `stream-1/19f2/RX0` | upper | 11.690312500 | 25.131963946–26.631963946 | +2 | `64875000 + 999` |
| `065355` | `stream-0/5d4d/RX0` | upper | 11.690312500 | 24.993036053–26.493036053 | +2 | `64500000 + 2164` |
| `103607` | `stream-0/5d4d/RX1` | lower | 11.459687500 | 52.650000000–54.150000000 | -1 | `133437500 + 1728` |
| `103607` | `stream-0/5d4d/RX0` | lower | 11.459687500 | 52.650000000–54.150000000 | +2 | `133437500 + 1728` |
| `103607` | `stream-1/19f2/RX1` | upper | 11.690312500 | 52.523433045–54.023433045 | +0 | `133187500 + 1735` |
| `130425` | `stream-0/5d4d/RX0` | lower | 10.959687498 | 49.969958477–51.469958477 | +2 | `126875000 + 1893` |
| `130425` | `stream-1/19f2/RX1` | upper | 11.190312500 | 49.837500000–51.337500000 | +0 | `126312500 + 2990` |
| `130425` | `stream-1/19f2/RX0` | upper | 11.190312500 | 49.837500000–51.337500000 | +3 | `126437500 + 1324` |
| `130425` | `stream-0/5d4d/RX1` | lower | 10.959687498 | 49.969958477–51.469958477 | +0 | `126687500 + 2725` |
| `150802` | `stream-0/5d4d/RX0` | lower | 10.959687498 | 4.033407381–5.533407381 | +1 | `11812500 + 24` |
| `150802` | `stream-0/5d4d/RX1` | lower | 10.959687498 | 4.033407381–5.533407381 | -1 | `11875000 + 857` |
| `150802` | `stream-1/19f2/RX1` | upper | 11.440312498 | 4.162500000–5.662500000 | -1 | `12250000 + 1964` |
| `150802` | `stream-1/19f2/RX0` | upper | 11.440312498 | 4.162500000–5.662500000 | +1 | `12125000 + 332` |

The local intervals differ between physical radios because their first-sample
UTC estimates differ. They name the same absolute-UTC interval.

## Leakage boundary

There are two distinct conditioning layers, and the final report must preserve
this distinction.

1. The Standard branch, alias, raw source, and frame lattice were already
   produced by GLRT64 products that used both even and odd Qin. The episode is
   consequently **not** an acquisition-blind or identity-blind holdout.
2. Inside this newly frozen episode, only even Qin may decide local frame
   support or fit any new rate/intercept. Odd Qin is a local held-out response:
   it cannot select a frame, alias, threshold, history, model, or capture.

Thus the experiment measures conditional cross-path repeatability and future
CFO prediction. It does not measure end-to-end acquisition yield, false alarm
probability, satellite identity, or unbiased physical Doppler truth.

## Frequency coordinate and clock limitation

For cross-band episodes, one physical range rate gives CFO rate proportional to
RF frequency. Each path's new frame CFO is therefore multiplied by

`11,000,000,000 / nominal_sky_frequency_hz`

before fitting a common rate. Nominal sky frequency is the applied IF center
plus the repository's documented 9.750 GHz LNB LO. This is only a nominal
coordinate. The manifests retain an uncalibrated frequency prior; LNB drift,
radio reference drift, and sample-clock scale are neither measured nor removed.
Separate constant intercepts absorb static offsets, but a time-varying clock
term remains inseparable from Doppler rate in this experiment.

## Frozen models

The primary episode model is

`normalized CFO(path, t) = intercept[path] + shared_rate × (t − t_ref)`.

It has exactly one slope and one constant intercept per exact receiver path.
It may not add a per-radio or per-path drift. A Huber IRLS fit uses tuning
constant 1.345, at most 50 iterations, and relative tolerance `1e-10`.

Two comparators use the identical even-selected masks:

- **separate robust rates:** one Huber slope and intercept per path;
- **fixed 500 ms causal line:** for each odd-Qin target, a path-local robust
  line fit to strictly earlier supported even-Qin measurements in the preceding
  500 ms, requiring at least 20 history frames.

The first 60% of the absolute-UTC episode supplies even-Qin training. The final
40% supplies odd-Qin response on frames whose even fold passed the frozen
support gate. A path needs at least 100 training frames and 50 held-out frames;
an episode needs two distinct physical radios. Every rejected capture/path is
retained in the failure ledger.

## Frozen outputs and interpretation

The execution must publish, per episode and in aggregate:

- the shared normalized rate and each separate path rate;
- maximum and RMS path-rate disagreement;
- deterministic 50 ms residual-block bootstrap rate uncertainty (500
  replicates, seed 418050);
- held-out odd-Qin RMS and median absolute CFO error on identical masks;
- the causal 500 ms comparator's future odd-Qin RMS;
- complete opportunity, support, rejection, and digest-verification ledgers;
- Matplotlib PNG figures and a machine-readable evidence receipt.

These are **measured estimator rates and disagreements**, not errors against a
known satellite truth. Sharing is preregistered as favorable only if its
equal-capture pooled held-out RMS beats separate rates, its bootstrap slope
uncertainty beats the median individual uncertainty, and no evaluable capture
is more than 10% worse in RMS. If both pooled ratios are at least one, the result
is adverse; all other cases are mixed. No threshold will be changed after odd
Qin is opened.

## Reproduction checkpoint

The response-blind validator is exercised with:

```bash
.venv/bin/pytest -q tests/analysis/test_multi_radio_common_rate_protocol.py
.venv/bin/ruff check \
  src/leo/analysis/research/multi_radio_common_rate_protocol.py \
  tests/analysis/test_multi_radio_common_rate_protocol.py
.venv/bin/mypy src/leo/analysis/research/multi_radio_common_rate_protocol.py
```

Raw execution is intentionally absent from this preregistration commit.
