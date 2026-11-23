# Proof-owner union rank transfer on two genuine short packets

The southern containing offer retained **39 of 1,618** screened cold orbits and reproduced all three ordered candidates, including the complete track assignments, satellite labels, signed aliases and rank scores. With the paid geographic proof included, CPU fell from **0.822 to 0.531 seconds**. DS30-0016 retained **23 of 1,449** and reproduced both available candidates exactly. Its frozen three-finalist guard invoked the original ranking, increasing charged CPU from **0.334 to 0.394 seconds**. [Frozen protocol](proof-rank-short-transfer-protocol.md) · [Numeric summary](measurements/proof-rank-short-transfer-summary.json)

| Genuine saved packet | Full proof catalogue / visited probes | Full / union cold roster | Full / union finalists | Proof + full CPU s | Proof + union attempt CPU s | CPU / elapsed s with guard |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0016 | 11,181 / 24 | 1,449 / 23 | 2 / 2 | 0.334 | 0.220 | 0.394 / 0.394 |
| Southern containing | 10,937 / 25 | 1,618 / 39 | 3 / 3 | 0.822 | 0.531 | 0.531 / 0.531 |

Both runs verified the original signed native digest, installed graph asset, offered region and causal archive. The fused geographic computation reproduced the archived installed-graph early decision fields exactly. DS30-0016 stopped on `eligible_exterior_separation`, and the south stopped on `inside_score`. The fused kernel processed all 24 and 25 visited probes, respectively, without projector fallback. The corresponding proof clocks were 0.159 and 0.299 CPU seconds. The proof always paid the complete original catalogue and prior. The union reduced only the orbit rows supplied to the later cold rank. [Complete proof rows and rank receipts](measurements/proof-rank-short-transfer.json.gz)

Cold scan construction and ranking cost **0.174 → 0.061 CPU seconds** on DS30-0016 and **0.523 → 0.232** on the southern containing packet, including each union's selector. The paired execution runs full first on DS30-0016 and union first in the south. The full path charges the proof and its own scan and rank. The reduced path also charges selection. When the guard invokes the original rank, the accounting includes both measured scan and rank costs and charges the proof once. These clocks cover the proof and rank boundary, excluding graph and catalogue preparation, finalist fitting, position fitting, the numerical grid and figure rendering.

DS30-0016 returned ordered scores of 773.793701626948 and 851.501600112712, with three assigned components in each candidate. The reduced order, scores and signed assignments were identical. The southern scores were 1083.650094593334, 1098.298211319704 and 1243.671440521904, with 22 assigned components per candidate. All three reduced scores and assignments matched them exactly. No full-rank finalist used a satellite outside the observed union on either packet. The observed equality covers these cold rankings. The separately tested dense short full solve changed science after the union, even with both subsequently lost satellite labels in its pool. [Dense union experiment](proof-global-rank.md)

## Archived southern far outcome

The existing installed-graph far receipt uses the identical short native packet and the released dense geographic projector. The genuine early proof evaluated all 96 probes. Each receiver independently selected `(-62.5, 0)` km, 50 km beyond the offered face, with gains of 0.894449 and 0.905053. The terminal reason is `both_receivers_support_far_exterior`, with both position arms absent and `withheld_early` before any cold rank or grid. The receipt check performed no new far proof or solve. [Archived installed-graph receipt](measurements/full-short-graph-transfer.json)

## Reproduce

Use the reviewed `proof_global_rank.py` from `b260c263e` with byte SHA-256 `297dd1fd485f4d439a9060b6661036094909bf8343bea533f6ace972185872a6`. The saved runner stops at an audit-only terminal after the two rankings. Thirty-two focused and adjacent tests passed. [Runner](proof_rank_short_transfer.py) · [Tests](../../../tests/pipeline_eval/test_proof_rank_short_transfer.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
here="$PWD/reports/ALGO08/v3"
out=$(mktemp -d /var/tmp/proof-rank-short.XXXXXXXX)
for case in physical south-inside south-far-receipt; do
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 35s \
    env PYTHONPATH="$here:$payload:$release/src:$release:$PWD" \
    OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    "$release/venv/bin/python" -BPs "$here/proof_rank_short_transfer.py" \
    "$case" "$out/$case.json" || exit
done
```
