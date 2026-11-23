# Sustained exterior descent catches India and misses both held omissions

The frozen rule withheld the India fix when the receiver was **1.5 km outside** and retained all five containing offers. It missed **both held 1.5 km omissions** and both 100 m omissions. The released far rule still withheld both 52.5 km omissions. The new screen failed its prespecified advancement criterion. [Frozen protocol](local-exterior-descent-protocol.md) · [Per-offer results](measurements/local-exterior-descent.json)

## Causal rule

The screen starts when the fixed-zero and fitted-calibration endpoints clip the same single face. It uses that face's three tangential rays from the released lattice. On either receiver, a score tie or reversal between 97.7 m inside and 97.7 m outside defeats the ray. Otherwise the rule checks whether the sequence from 3.125 km inside to 3.125 km outside rises through all four original points on both receivers. The farther exterior point must also beat every one of the 48 original sampled interior points on both receivers. It reuses scored coordinates and stops once every exterior candidate is defeated. The check leaves existing far withholding in place and makes no claim about unsampled interior points or calibrated error rates. [Implementation](../../../tools/pipeline_eval/variants/experimental/local_exterior_descent.py) · [Original regional mixture](../single-core-2x/regional-reassignment.md)

## Held offers and work

India and the two public 100 m boundary pairs are development inputs. The original North and South offers are distinct archived 25 km squares tested after the freeze. The geographic labels in the earlier reports were public. The held comparisons use original digest-verified signed v2 terminals. Their detector document digests differ from the map receipts. A direct comparison verified the ordered winning observations, identities, receivers, RF, timestamps and clock source used for Graph coefficients. India and the 100 m pairs use matched detector digests for maps and endpoints. [Original terminal predictions](../regional-release/predictions.json) · [India receipt](india-regional-diagnostic.md) · [Mirrored offers](../single-core-2x/mirrored-regions.md)

| Offer | Reference clearance | Screen result | Added unique scores after the released far rule |
|---|---:|---|---:|
| India, containing | +3.576 km | Retained, both endpoints interior | 0 |
| India, omitted | −1.500 km | Withheld, common exterior at 3.125 km | 52 |
| North, near face | +0.100 / −0.100 km | Interior competitor in both offers | 12 / 12 |
| South, near face | +0.100 / −0.100 km | Both endpoints interior in both offers | 0 / 0 |
| North, held containing | +5.797 km | Retained, both endpoints interior | 0 |
| North, held omitted | −1.500 km | Interior competitor | 15 |
| South, held containing | +5.891 km | Retained, both endpoints interior | 0 |
| South, held omitted | −1.500 km | Sustained exterior rise failed | 12 |
| North and South, far | −52.500 km each | Released far veto withheld both | 0 / 0 |

On the India omission, the accepted common exterior point beat the best sampled interior by **0.010267 / 0.010478** per original observation for receivers 1 and 2. The combined route consumed **78 distinct scores**, including the 26 already paid by the released far check. The northern held omission's only sustained ray pointed to `(−15.625, +5)` km, and the interior point `(−3.125, −5)` km beat it by **0.018475 / 0.007542**. On the center ray both scores rose immediately across the northern face, by **0.000171 / 0.000372**, and then fell before 3.125 km outside. All three rays on the southern held omission showed immediate bilateral rise. None showed sustained bilateral rise. Even the closest remaining ray lost **0.000086** in receiver 2 at the farther exterior point. [Per-ray gains, competing coordinates and score counts](measurements/local-exterior-descent.json)

The distance requirement loses exterior maxima close to the face. The earlier unrestricted bilateral comparison had positive gains on both held omissions, with maxima just 97.7 m beyond the face. This weaker evidence is already documented. A 100 m omission can also leave both signed endpoints in the interior. The frozen screen therefore provides evidence for the wider India signal and fails on the two held offers at the same truth clearance. [Original all-track comparisons](../single-core-2x/regional-reassignment.md)

The additional callback work above counts unique evaluations assuming a shared cache within the prepared geometry. Offline rule and cache readout took less than 0.3 CPU ms per offer. The archived complete probe passes used about **0.81–1.45 CPU seconds**, combining the geometry and actual score evaluation. This comparison used cached original scores. The marginal cost of recomputing the extra scores live was unmeasured. Every fit and its two calibration arms came from a prior publication. The regional mixture score removes a constant within a fixed-RF track, so the fitted `c` contributes no separate directional evidence. [Archive CPU clocks and both calibration arms](measurements/local-exterior-descent.json)

## Reproduction

Use the existing tmpfs native archives and a fresh tmpfs output directory. Open references only after the prediction document has closed. Thirty-nine component and related guard tests passed. [Replay and scorer](local_exterior_descent_trial.py) · [Component tests](../../../tests/pipeline_eval/test_local_exterior_descent.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
out=$(mktemp -d /dev/shm/leo-exterior-descent.XXXXXXXX)
script=reports/ALGO08/v3/local_exterior_descent_trial.py
export PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD/src:$PWD"
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
locked() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c 2 -n 7 taskset -c 2 "$@"
}
locked "$release/venv/bin/python" -BPs "$script" run "$out/predictions.json"
locked "$release/venv/bin/python" -BPs "$script" score "$out/predictions.json" "$out/scored.json"
```
