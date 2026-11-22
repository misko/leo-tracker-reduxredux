# Disproving the far-exterior veto early

The terminal-only evaluator reproduced all ten archived veto decisions. It computed **25 of 96 scores** on each of the eight cases that kept their fix. It computed all 96 in each far omission and reproduced the original receiver maxima, gains and separation exactly. The six offers that activated the original optimizer-bound gate would require **292 scores instead of 576**. The four other offers would still bypass the scorer. [Saved-packet and timing receipt](measurements/regional-veto-short-circuit.json) · [Archived boundary activations](regional-bound-guard.md#saved-path-audit)

## Why the decision is exact

Validate the coordinates and side of all 96 probes up front. Score the exterior probes at least one width beyond the offered face first. Each receiver's maximum on that set is the best possible eligible exterior winner. If an inspected inside score reaches that maximum, the receiver cannot show a strictly positive exterior gain. If an inspected ineligible exterior score reaches it, the exterior winner is either tied or ineligible. An eligible tie or two unique eligible maxima more than one width apart also defeats the veto. Later scores leave those disproofs valid. The remaining probes are visited in the original geometric order, starting with the innermost inside shell. That first inside probe was sufficient in each of the eight saved non-veto cases. [Original exact rule](../../../tools/pipeline_eval/variants/experimental/regional_exterior_veto.py) · [Short-circuit evaluator](../../../tools/pipeline_eval/variants/experimental/regional_veto_short_circuit.py)

The opt-in `regional_reassignment.evaluate_veto(prepared, catalogue, region)` uses the same causal geometry screen over **all 96 locations**, the same full-catalogue mixture denominator and the original arithmetic at each inspected point. A true veto requires all 96 valid scores and runs the original reducer, including its tie and separation rules. Invalid layouts and malformed inspected scores fail open. After a disproof the Boolean is final, while the readout has `complete=false` and a stop reason. An uninspected malformed value could still make the full diagnostic incomplete. Call the existing full evaluator whenever the receiver maxima, gains, or pointwise owners are required. [Opt-in and full scorer](../../../tools/pipeline_eval/variants/experimental/regional_reassignment.py) · [Tie, malformed-score and all-location tests](../../../tests/pipeline_eval/test_regional_veto_short_circuit.py)

## One matched northern guard-stage timing

On the saved public northern 100 m inside offer, CPU fell from **1.278 s to 0.472 s**, saving **0.806 s**. Both calls started from the same prepared Graph packet and already-built causal catalogue. Both included the all-location geometry setup and invoked the real probe scorer. The full call ran first and its complete score rows matched the pinned archive exactly. The terminal-only call stopped at probe 25 with the same decision. Fifty-two tests passed. This timing covers only the activated guard stage on that saved offer. [Timing receipt](measurements/regional-veto-short-circuit.json) · [Previously tested projection packing](guard-projection.md)

## Reproduction

The default trial reads the ten pinned saved score packets. Add `--time-north` to rebuild and time the scorer from the original northern detections and causal archive.

```bash
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
north=("$bench"/covariance-north-inside/baseline/fast-scan-automatic-work/*/detections.json)
archive=/tmp/leo-regional-qZJKBw4W/public/tle
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  env PYTHONPATH="$PWD:$PWD/src:$release" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$release/venv/bin/python" -B -m reports.ALGO08.single-core-2x.regional_veto_short_circuit_trial \
  --time-north "${north[0]}" "$archive" "$release/assets/tracks.json"
```
