# Does using more recorded carriers strengthen identity transfer?

The previous rate-comparable test used four carriers per edge, discarding much
of the 10 MS/s recordings. This follow-up tests the independent possibility that
the limited spectral intersection hid a useful header fingerprint. It adds
previously excluded coordinates while retaining the fixed frame split and
controlled comparison protocol; it does not repeat a blind alignment search.

## Coverage and features

The fixed 10 MS/s subset contains 709 qualified, deduplicated observations:
397 DS10, 212 DS9, 43 DS8 and 57 DS7. There are 121 candidate-labelled entries.
The common support is determined without inspecting feature scores or labels:

- Upper edge: bins 473–487 and 496–506.
- Lower edge: bins 516–527 and 536–549.

Both have 26 nonpilot carriers. Six early symbols therefore supply 156 complex
samples or real signs per frame, compared with 24 in the four-carrier baseline.
No pilot or late T-code samples enter these features. Adjacent-carrier phase
products do not bridge the gap occupied by pilots.

Four frozen representations are compared: the original four-carrier signs,
26-carrier unit phase, adjacent-carrier phase differences over the wider support,
and 26-carrier signs. Instrument-stratum centering/scaling uses only first-half
observations; cross-frame comparisons, label authority, matching and grouped
permutations are unchanged from the initial study. All recordings have been
previously inspected, so these are computational holdouts, not new confirmation
data. The inherited four-carrier-specific symbol-2 ablation is omitted here.

## Outcome

Strict same-receiver/rate/channel comparisons have no positive pair in this
subset. Allowing different receivers while matching their instrument pairs gives
29 same-candidate pairs; 14 have matched different-candidate controls. Those same
14 pairs are used for every representation:

| Representation | Same-candidate similarity excess | Session-preserving adjusted p |
|---|---:|---:|
| Four-carrier real-sign baseline | +0.1036 | 0.080 |
| 26-carrier unit phase | +0.0245 | 1.000 |
| Wider adjacent-carrier phase products | −0.0053 | 1.000 |
| 26-carrier real signs | +0.0224 | 1.000 |

The trajectory-preserving maximum-statistic control gives p=1.0 for every
representation. Strong-tier-only comparisons and cross-session/channel
comparisons lack matched positive coverage. Their abstentions must not be read
as negative identity results. Corrections cover four feature families and eight
scope/tier cases within this exploratory follow-up, not every historical test.

Using 6.5 times as many early coordinates does not improve the matched similarity
effect under this representation. The short-term lead is more concentrated near
the original carrier positions. Possible explanations include poorer outer-carrier
recovery, different data content or nuisance structure near the pilots; the test
does not distinguish them. It does not show that the extra carriers carry no
information, nor that a weighted or coded decoder could never exploit them.

No address, counter, timing field, unique satellite fingerprint or message bytes
were decoded. This result weakens the immediate hypothesis that simply retaining
all common 10 MS/s header signs makes the existing identity lead clearer.

## Reproduction

`bandwidth_extension.py` verifies the sealed row metadata and every source-cache
hash, determines common support, computes the four representations, and calls
the unchanged `corpus_identity.experiment` protocol. It records the protocol's
source hash and its own hash. The script sets feature names in its own process;
it does not modify the prior protocol or its results.

Outputs are ignored `local/bandwidth-extension/{features.npz,summary.json}`.
The component-owned synthetic test confirms that added carriers contribute to
the wide representation while the pilot gap is excluded from adjacent-pair
features. The test and Ruff pass. No RF collection, fixture changes, commits or
remote publication occurred.
