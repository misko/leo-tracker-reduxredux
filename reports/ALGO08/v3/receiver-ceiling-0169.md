# DS30-0169 first-member receiver budget

The verified 20/12 ms schedule processed the same resident member at **264.8 and 259.7 MB/s** in opposite orders. Released 20 ms acquisition reached **181.4 and 176.1 MB/s**. The mixed path cleared the conditional **207.46 MB/s** target in memory. The original member had zero pages resident and its one verified copy took **1.446 s**. Charging that copy and the mixed acquisition gives **45.21 and 45.06 MB/s** for the measured staged path. These results price one member and provide no whole-recording cold throughput or position qualification. [Frozen scope](receiver-ceiling-0169-protocol.md) · [Timing and factor receipts](measurements/receiver-ceiling-0169.json.gz)

## Input and clocks

The first signed member contains 78,852,856 compressed bytes, a 173,459-byte index and 102,400,000 decoded bytes. All arms verified the original manifest, index, compressed payload, 64 individual I/Q digests, and the complete decoded member. The same 51 stereo visits were admitted and 13 excluded. Each fresh process ran the released bounded acquisition with its normal compressed buffer, paired SHA-256 and admission rules. The one-member scope submitted no lookahead. Four replays used the same tmpfs copy, which had all 19,252 pages resident before and after each acquisition. The original read made all 19,252 source pages resident and accounted for 154,016 input blocks. Reads were confined to this member plus its metadata, with no eviction or further waveform acquisition. [Driver and bounds](receiver_ceiling_0169.py)

| Order | Arm | Verified acquisition elapsed, s | Acquisition CPU, s | Native CPU, s | Acquisition MB/s | Worker launch to exit, s |
|---|---|---:|---:|---:|---:|---:|
| Full then mixed | Full 20 ms | 0.435 | 0.433 | 0.288 | 181.4 | 2.318 |
| Full then mixed | Mixed 20/12 ms | 0.298 | 0.298 | 0.146 | 264.8 | 2.318 |
| Mixed then full | Mixed 20/12 ms | 0.304 | 0.303 | 0.152 | 259.7 | 2.469 |
| Mixed then full | Full 20 ms | 0.448 | 0.448 | 0.300 | 176.1 | 2.472 |

The mixed acquisition saved **0.137 and 0.144 s** on the resident member. The worker elapsed column charges separate launch, imports, pin verification, audit packet writing and exit for each experimental arm. Publication would amortize those launch costs across members. The one-time source copy includes reading, verifying the compressed SHA-256 and writing to tmpfs. Its copy-only rate was **54.52 MB/s**. The staged rate adds the copy and acquisition clocks and includes the local reread. There was no direct cold receiver-on-origin comparison. [Raw and resource clocks](measurements/receiver-ceiling-0169.json.gz)

The target uses the historical cold complete time of **73.673 s**, the independent saved detector publication clocks of **17.893 s named and 11.822 s combined**, and **5,189.509 MB** of original compressed data. Half the historical time leaves **25.0145 s** for safely acquiring the complete recording if combined publication takes the same time on the changed packet. At the resident mixed prefix rates, acquisition would take **19.60–19.99 s** if those rates transferred. The single cold origin read shows the storage bandwidth can be materially lower. The original read, cache dispersion, capture exclusions, admitted DSP cost, and publication on changed evidence remain open across the full recording. [Recorded conditional budget](measurements/receiver-ceiling-0169.json.gz)

## Signed factors and final named owners

The mixed schedule used eight full stereo anchors and 43 short stereo primaries, with no skipped admitted visits. Native factors retain their actual emitted order and signed values. The selected rows record what each acquisition hands to localization. Released acquisition uses causal continuation, while the mixed callback selects the strongest verified factor and has no causal-history gate. A corresponding factor matches within two wrapped native samples and 250 Hz signed CFO on the same visit and lane. The comparison keeps exact tuple bytes and native rank as separate checks. [Ordered lane vectors](measurements/receiver-ceiling-0169.json.gz)

| Boundary | Mixed lane aperture | Named / mixed factors | Common | Missing from mixed | New in mixed | Wire-exact common |
|---|---|---:|---:|---:|---:|---:|
| Native | 20 ms anchors | 21 / 21 | 21 | 0 | 0 | 21 |
| Native | 12 ms nonanchors | 89 / 45 | 43 | 46 | 2 | 0 |
| Selected | 20 ms anchors | 0 / 11 | 0 | 0 | 11 | 0 |
| Selected | 12 ms nonanchors | 15 / 45 | 13 | 2 | 32 | 0 |

Native anchor order matched exactly. Of the 43 matched native short factors, 38 kept their original rank. The 11 new selected anchor factors came entirely from selection. Of the 43 new selected mixed factors in total, 42 are at formerly unselected lane counters and one replaces a different carrier at the same counter. [Signed factor and selection evidence](measurements/receiver-ceiling-0169.json.gz)

The fresh full path reproduced all 102 ordered probe dictionaries, excluded windows and delivery clocks in the first member of the sealed named packet. The audit used the released winning-observation adapter and verified the identity join against the exact receiver, channel, hardware counter, RF and signed CFO. The matched stock solve contains 2,236 ordered owners in each calibration arm. Of the 15 named-selected prefix factors, **seven have an owner in both arms**, four conditional and three predictive. All seven were among the 13 approximate mixed matches. The 13 matches have absolute CFO differences of **1.108–117.781 Hz** and wrapped epoch differences of **0.01775–0.84808 samples**. They preserve approximate carrier evidence with changed measurement values. [Bound named detector and owner audit](measurements/receiver-ceiling-0169.json.gz)

Neither lost selected factor had a final owner in either arm. Visit 48, receiver 1, channel 1 had a named +262,804.575 Hz primary and an empty mixed lane. Visit 58, receiver 0, channel 3 went from a named −331,321.502 Hz rank-1 factor to −194,363.477 Hz rank 0 at the same hardware counter. Neither named factor was present in the mixed native output. Ownership in the named solve cannot determine the effect of the 43 newly selected factors. Their signed measurements can change track formation, ownership and both likelihood fits, so a complete matched solve on the changed recording would be needed to establish either position or RF effects. This experiment ran no solve. [Original owner order and roles](measurements/receiver-ceiling-0169.json.gz)

## Reproduction

The compact timing and offline owner receipt SHA-256 is `ee76714eca005b03acd4b477172e9aafe9f38861f79dfe1c2294f323979e390e`. The command below replays the original bounded trial in a fresh tmpfs directory. For the historical result, the `audit-owners` step read only the already saved receiver packets and the sealed named solve receipt. Nine component tests cover member confinement, hash and length checks, signed matching, exact anchor parity, independent selection differences, and ordered owner validation. [Tests](../../../tests/pipeline_eval/test_receiver_ceiling_0169.py)

```bash
install_root=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
out=/dev/shm/leo-receiver-ceiling-0169-rebuild
gauss() {
  flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
    TMPDIR=/dev/shm PYTHONPATH="$install_root/src:$PWD:$PWD/src:$install_root" \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$install_root/venv/bin/python" -BP -m reports.ALGO08.v3.receiver_ceiling_0169 run "$out"
gauss "$install_root/venv/bin/python" -BP -m reports.ALGO08.v3.receiver_ceiling_0169 audit-owners "$out"
gauss "$install_root/venv/bin/python" -BP -m pytest -q -p no:cacheprovider \
  --basetemp=/dev/shm/leo-receiver-ceiling-0169-rebuild-tests tests/pipeline_eval/test_receiver_ceiling_0169.py
```
