# Deployed fractional scores on the spectral receiver

The absolute-phase verifier restored all 79 ordered factors on the saved DS26 weak, Austin, and three DS30-0008 regression lanes. On the chronological DS30-0016 prefix it restored all 152 factors and all 53 causal selections, including one residual carrier. The comparisons include rank, integer epoch, fractional offset, signed CFO, and both continuous scores. [Receipts](measurements/receiver-fractional-absolute-score.json.gz)

The verifier uses the scout CFO that enters fractional verification. The published CFO already includes a residual term and would give a different oscillator phase. The exact path retains the deployed operations for each absolute sample position, rounded Lanczos weight row, sine and cosine, fused complex multiplication, and original summation chains. It uses the existing packed correlation arithmetic with one frame of scratch at a time. A zero winning bin implies an exactly zero residual, so the calculation skips sorting the positive symbol time steps on that path. Other winning bins use the original median arithmetic. Native timing, the signed cancellation pass, and both verification calls still use their original inputs. The all-factor receiver replaces only the verifier object and preserves its public symbols. [Exact correlator](../../../tools/pipeline_eval/variants/experimental/receiver_fractional_exact.inc) · [Pinned builder](receiver_fractional_exact_trial.py)

| Matched inputs | Lane calls | Ordered factors | All-factor native CPU change from `b63cf5b0…` |
| --- | ---: | ---: | ---: |
| DS26 weak stereo | 36 | 58 | +17.63% |
| Austin measured, zero or shifted mixer center | 8 | 16 | +17.05% to +20.98% |
| Austin phase nulls, zero or shifted mixer center | 8 | 0 | −1.65% to +0.17% |
| DS30-0008 regression windows | 3 | 5 | +17.67% |
| DS30-0016 first 128 visits | 232 | 152 | +9.33% |

The three dense lanes reproduce all five deployed factors with CFO and scores equal byte for byte. The archived full DS30-0008 publication retained rank 0 at visits 2661, 3298, and 3869 in both the deployment and the terminal-guard predecessor. The restored detector reproduces the deployed retained tuples. The isolated replay has insufficient history to regenerate the archived votes. The chronological DS30-0016 prefix retained 116 of its 128 visits through capture-quality checking and reproduced the deployed preference, votes, selection, and selected bytes on four balanced repeats. [Saved evidence and input pins](measurements/receiver-fractional-absolute-score.json.gz)

## Selected-score publication

The published probe contract stores zero or one selected carrier. The opt-in detector keeps its normal native candidate list and invokes the stock continuation rule once per lane. With two factors it restores both exact margins before continuation and orders them by exact margin and scan rank, including rank-order ties. A single factor needs the exact scores only when continuation retains it. The repair binds the current lane workspace, scan rank, integer epoch, offset, and original scout CFO. Each native measurement clears the repair state before use, including empty and failed requests, and a new acquisition opens a new continuation context. The receipt reports actual repairs and already exact rows outside the scientific payload. [Bridge](../../../tools/pipeline_eval/variants/experimental/fractional_score_selection.py) · [Resident native repair](../../../tools/pipeline_eval/variants/experimental/receiver_fractional_selected.inc)

The earlier diagnostic repaired only after selection. Its +3.36% native CPU result included 53 repairs averaging 0.541 ms, versus +9.33% for all-factor exact, on the same chronological prefix. As a publication design it can pick a different output when the approximate margins reverse a tie. A generated witness assigns three votes to the exact rank-0 winner and two to rank 1. An approximate reversal selects neither under the released vote rule. The implemented publication bridge restores rank 0 before applying that rule. The selected-score receiver still uses the parent's guarded approximate verifier to establish eligibility and bins. Its native exact fallbacks guard the acceptance margin, the strong-margin threshold, competing spectral peaks, and uncertain two-factor order. The saved comparisons and probe test establish local parity. The parent guard is an engineering floating-point bound. [Guard](../../../tools/pipeline_eval/variants/experimental/receiver_phase_free_verify.inc) · [Native score and state checks](../../../tests/pipeline_eval/test_experimental_receiver_fractional_exact.py) · [Continuation tie witness](../../../tests/pipeline_eval/test_fractional_score_selection.py)

The frozen publication entry opened a fresh acquisition on the same prefix and compared four balanced cycles. The all-factor and selected-score arms each reproduced the 232 deployed probe rows byte for byte, including all 53 selected rows. They also preserved the raw authority, clock records, and the 12 capture-quality exclusions. Per repeat, the selected-score bridge used 79 exact repairs on 41 two-factor lanes, kept three already exact rows, and repaired 30 retained singles. Median process CPU at the acquisition boundary was **511.74 ms** on the parent, **576.48 ms** for all-factor exact and **584.98 ms** for selected score. The paired changes were +12.80% and +13.12%. The published bridge provided no speed advantage over all-factor exact on this prefix. [Bounded acquisition receipt](measurements/receiver-fractional-absolute-score.json.gz)

## Frozen controls

The all-factor bundle is `integration-fractional-absolute-all`, specification `sha256:a546069457b70491949d3b500f65cffd26939e693d9079ddc6b37a55d26e2afa`. It has receiver SHA-256 `2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5`. The selected-score bundle is `integration-fractional-absolute-selected-v3`, specification `sha256:e819d432e87d84f9f03e6df8e147fc7d2894e776c1db9e23e9b84113cb1e9e71`. It has receiver SHA-256 `a5862937b78f13d9788386d134cdbe427393dab678c858f27d4efeacdbf0efcb`. Both are research successors to `445744b4…`. The builder relinks the parent exactly from pinned objects. The freezes verify the archived verifier and new compilation artifacts, pin all changed bundle sources, and verify inherited bytes. The selected-score launcher checks the exact library bytes and loads its own private copy. An unsupported schedule, mismatched library, or absent score-repair ABI fails before eligible factors are published. [Freezer](freeze_fractional_exact_receiver.py) · [Bounded acquisition runner](receiver_fractional_selection_trial.py)

The prefix command exercises the frozen launcher setup and the normal acquisition entry. It decodes the previously studied sealed prefix once and compares resident acquisition calls. It terminates before solving or publication. The timing holds the shared Gauss lock and uses one CPU and one numerical thread.

```bash
bench=/tmp/leo-algo08v2-2x-bench
repo=/tmp/leo-algo08v2-2x
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
selected="$bench/integration-fractional-absolute-selected-v3"
flock -n "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 60s \
  sudo -n -u leo -- env OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$selected:$release/src:$release" \
  "$release/venv/bin/python" -BPs \
  "$repo/reports/ALGO08/single-core-2x/receiver_fractional_selection_trial.py" \
  "$selected" "$bench/integration-spectral-vectors-wrapped-longitude" \
  "$bench/integration-fractional-absolute-all" \
  /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0016.json /srv/bulk
```
