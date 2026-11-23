# Representative satellite families for full-observation signed solving

The representative pool cut the dense cold attempt to **4.009 CPU s**. Its full-catalogue check then found a compatible omitted family on two original tracks. The checked full signed fallback brought the total to **42.744 CPU s**, above both the 39.045 s full signed control and the 24 s target. The southern containing run also needed full fallback. The southern displaced offer withheld directly, with a fine-salvage rescan on eight of ten tracks. [Numeric summary](measurements/representative-family-pool-summary.json) · [Sealed receipts and owner rows](measurements/representative-family-pool.json.gz)

## Saved outcomes

| Offer | Stock CPU (s) | Full signed CPU (s) | Charged pool CPU / elapsed (s) | Returned route | Grid points | \(c=0\) error, stock → returned (km) | Fitted \(c\) error, stock → returned (km) | RF RMS returned, zero / fitted (Hz) |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| DS30-0008 | 60.966 | 39.045 | 42.744 / 42.748 | Full signed fallback | 179 | 1.639 → 1.086 | 1.512 → 1.080 | 128.821 / 128.753 |
| South containing | 4.620 | 3.878 | 4.754 / 4.754 | Full signed fallback | 137 | 0.817 → 0.817 | 1.101 → 1.101 | 6.502 / 6.392 |
| South displaced | 6.400 | 6.794 | 6.866 / 6.866 | Direct withheld | — | — | — | — |

Both containing fallbacks matched the sealed full signed arms, owner digests, reason and scientific grid and path digests. Both objective replay gaps were zero on each return. On dense, all 4,440 published rows per arm matched signed full. Of 4,472 stock rows, 4,358 remained with the same satellite and role, 114 were absent, and 82 new rows appeared under the full signed fallback. Dense returned RF RMS was 0.882 / 0.910 Hz below stock. On the southern containing offer all 266 rows, roles and RF values matched stock. The southern displaced route completed its signed fit and withheld with the existing two-receiver exterior check. The containing results demonstrate effective fallback; the restricted proposal supplied neither returned fix.

## Catalogue coverage and charged work

| Offer | Representative / curved tracks | Pooled / full catalogue | Restricted rank CPU (s) | Exact cold finalist CPU (s) | Full fixed-state check CPU (s) | Full fallback CPU charged (s) |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0008 | 45 / 111 | 47 / 1,476 | 1.897 | 1.679 | 0.261 | 35.130 |
| South containing | 14 / 14 | 20 / 1,618 | 0.153 | 0.025 | 0.014 | 2.475 |
| South displaced | 14 / 14 | 20 / 1,612 | 0.250 | 0.069 | 0.013 | — |

The dense full-time check identified NORAD 63476 on two original receiver 2, channel 5 tracks. The full signed fallback published 20 conditional rows attributed to that family per arm. The southern containing check found NORAD 65444 on both receivers' channel 3 tracks despite using every curved track to nominate the pool. Its failure shows that full representative coverage alone did not fix the shape ranking. Neither containing rejection was caused by a near-tied compressed branch. The pooled cold zero-reference scores differed by 652.076 units on dense and 46.056 on south containing.

The direct displaced run evaluated 52 pooled fine-salvage candidates and rescanned 218 outside-pool candidates. It skipped only 50 of the 320 original shortlist entries. The eight rescans used 0.199 CPU s, and the inside passes used 0.057 s. Total salvage was 0.466 CPU s versus 0.320 s on the matched full signed route. The full-catalogue dense fallback listed 1,018 fine-salvage evaluations across 32 tracks. Seven tracks had no surviving support even after the entire shortlist was evaluated. The dense restricted attempt stopped before its own salvage, leaving its dense rescan cost unmeasured.

The measured full signed dense route used 13.962 CPU s in cold work, 5.053 s in salvage and 20.030 s in other work. Substituting the measured 4.009 s restricted attempt and granting a zero-cost salvage gives **24.039 CPU s** at the matched other-stage rate. This projection assumes unchanged follow-on costs and a successful pooled proposal. The measured route used the more expensive fallback instead. At those stage rates, even free salvage would leave no budget for a new ranking rescan.

## Approach

The proposal groups original curved Graph tracks by receiver, actual RF and the time third containing the track midpoint. Each group nominates through its longest complete track. Every representative is compared with the full causal catalogue at the supplied offer centre. The proposal profiles an intercept, drift and a bounded phase derivative over every original timestamp, checks visibility over the whole measured track, and nominates its four best supported catalogue rows. The released centre and corner search then runs on the union of those rows using every point on every original track. [Frozen protocol](representative-family-pool-protocol.md)

The compact rank preserves original NORAD identity and discrete aliases when its leading branch enters the two original exact refinements. A near-tied exact centre objective or compatible outside-pool nomination at the refined state invokes full signed inference. The later salvage still computes released coarse shortlists with every causal catalogue row. Its exact fine pass tries pooled candidates first at all original support times. It evaluates the rest of the original shortlist whenever the first pass finds no support, finds only trimmed support or has a close equal-length runner-up. The same branch compatibility, 5% repair, exact signed arms, displaced-region check and numerical objective replay govern the terminal decision. No observation is removed by the proposal.

The earlier blind-rank work shares exact centre arithmetic over the entire catalogue. Track moments approximate full-catalogue timing statistics, and quadrature thins observed times through recovery. This test instead restricts which satellite families enter the expensive initial ranking and bounds the work spent on the fine salvage shortlist. The fixed-state outside check and salvage recheck cannot prove that no excluded satellite would win under another jointly fitted position or phase. [Cold rank reuse](blind-rank.md) · [Track moments](../single-core-2x/solver-track-moments.md) · [Track quadrature](track-quadrature.md)

The first implementation attempted to evaluate the installed native orbit stencil with the unbound Python projector and stopped before a result. The measured source obtains the projector and geometry at the installed numerical boundary. The frozen schedule, costs and gates were the same. Each scored run used the original sealed detections and causal region. The stock and full signed controls are separately sealed same-input solves from the quadrature trial. Their CPU clocks are comparisons from that earlier session. The new clocks measure from saved detections through standard numerical evidence or withholding. They exclude waveform acquisition and PNG encoding.

## Reproduce

Use the installed runtime and archived inputs under the shared Gauss lock. Write the three results to a new writable directory and then score the sealed outputs.

```bash
runner=reports/ALGO08/v3/representative_family_pool_trial.py
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
out=$(mktemp -d /var/tmp/family-pool.XXXXXXXX)
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 125s \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
for case in DS30-0008 south-containing south-far; do
  gauss env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release" \
    "$release/venv/bin/python" -BPs "$runner" run "$case" "$out/$case.json" || exit
done
gauss env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src" \
  "$release/venv/bin/python" -BPs "$runner" score "$out" "$out/summary.json" "$out/full.json.gz"
```
