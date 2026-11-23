# Held-carrier recall from a solved sparse RF pass

A dense sparse solution supplied a satellite and same-receiver anchor within 60 seconds for **1,715 of 2,920** unpaid full-v3 owners. Requiring the same tuned RF reduced that metadata ceiling to **168**. The best two-slot signed-CFO rule matched **234 of 2,920** held owners within 4.55 kHz while asking for **1,620 stereo revisits**. It matched zero of 152 held owners on the independent southern recording. These comparisons stop at signed CFO. [Frozen protocol](sparse-rf-recall-protocol.md) · [Measurements](measurements/sparse-rf-recall.json) · [Proposed visit sets](measurements/sparse-rf-visits.json.gz)

## Coverage from solved labels

Both replays reproduced the frozen first-pass endpoints, exact owner digests and scientific path and grid. The dense solve published 1,416 observations per arm across 16 satellites. It shared 1,289 native observation IDs with full v3, with 1,256 matching satellite labels and 33 different labels. Of the 3,183 missing full-v3 observations, 2,920 were on unpaid stereo visits, 36 were on paid warm-ups, and 227 were on searched visits. The southern solve shared all 114 published sparse owner labels with v3, covering three satellites. Its other 152 v3 owners were all on unpaid visits and belonged to satellites absent from the sparse solution. For each input the two calibration arms had the same metadata counts. [Frozen block experiment](measurements/rf-block.json)

| Unpaid held owner support | Any time | Within 60 s | Within 30 s | Within 8 s |
|---|---:|---:|---:|---:|
| Dense satellite among sparse owners | 1,833 | 1,808 | 1,645 | 1,450 |
| Dense same satellite and receiver | 1,716 | 1,715 | 1,642 | 1,428 |
| Dense same satellite, receiver and exact RF | 192 | 168 | 134 | 44 |
| Southern satellite among sparse owners | 0 | 0 | 0 | 0 |

These ceilings grant knowledge of the correct held satellite at scoring. The proposal stage receives only sparse solved labels and admitted probe metadata. Unlike the earlier anchor-sky experiment, this test begins with fitted first-pass satellite ownership, receiver parameters and an estimated position on the same scan. [Earlier anchor-sky test](anchor-sky.md) · [Native ownership join](primary_owner_census.py)

## Two-slot signed carrier proposals

The candidate projects causal orbit Doppler at the sparse fitted site using each sparse family's fitted orbital phase. It adds the released receiver hardware and smooth terms. In every anchor it measures the signed residual and separates the nearest integer GLRT period. The exact-RF rule transfers the median local residual for the same satellite, receiver and RF branch. The RF-transfer rule may use local observations of the same satellite on the same receiver at another frequency if the target receiver and RF show that signed branch within 60 seconds. It sorts by local distance, descending support, and a stable satellite and alias key. The model evaluates at most two ranked satellite and branch hypotheses per antenna window. Full-v3 ownership and observed held CFO enter only after both arm proposals are generated. [Prototype](sparse_rf_carrier.py)

| Input and rule | Proposed antenna lanes / hypotheses per arm | Correct owner in shortlist, `c = 0` / fitted | Correct owner and ≤400 Hz, `c = 0` / fitted | Correct owner and ≤4,550 Hz, `c = 0` / fitted |
|---|---:|---:|---:|---:|
| Dense, exact RF | 2,775 / 4,148 | 168 / 168 | 150 / 148 | 168 / 168 |
| Dense, RF transfer | 2,775 / 5,550 | 234 / 234 | 167 / 216 | 234 / 234 |
| Southern, exact RF | 56 / 56 | 0 / 0 | 0 / 0 | 0 / 0 |
| Southern, RF transfer | 56 / 110 | 0 / 0 | 0 / 0 | 0 / 0 |

At 4,550 Hz the dense transfer predictions had 279 and 280 absolute signed-frequency matches if the label was ignored. Requiring the full-v3 satellite gives 234 in each arm, **8.0%** of the unpaid held owner factors. At 400 Hz the stricter owner counts were 167 and 216. Each arm spent about 0.10 dense CPU seconds or 0.005 southern seconds generating both proposal sets. Timing or waveform confirmation could only reduce the measured joint owner-and-frequency eligibility for these proposals. [Both calibration arms](measurements/sparse-rf-recall.json)

## Stereo revisit and CPU obligation

Each dense rule and arm queried the same 1,620 distinct stereo visits, including 1,027 with an original selected factor on a queried antenna. The 4,550 Hz transfer matches spanned 208 visits in each arm. At 400 Hz they spanned 160 and 194. Both southern rules queried 28 visits, all with empty original factors on the queried antennas. The decoded probe payload for those visits is **2.592 GB dense and 44.8 MB south**, charging each stereo window once. Holding every unpaid probe until the first fitted solution exists would require **7.123 GB dense and 1.248 GB south** of decoded probe payload. A receiver can instead reopen the sealed members containing the eventual queries. The exported visit IDs support that member-level accounting. [Visit manifests](measurements/sparse-rf-visits.json.gz)

Prorating the measured 37.34 dense detector CPU seconds by the first pass's 2,313 paid visits gives 12.77 seconds of native callback work. Keeping the measured 21.62 seconds outside receiver callbacks and the original 10.29-second sparse solve leaves **10.86 CPU seconds** to reach half of the archived 111.08-second v3 CPU time, before charging revisits, verification, a new fit or final publication. Searching all 4,452 unpaid visits at the same mean callback cost would add about 24.57 seconds. The earlier original two-slot directed verifier spent 1.746 ms per positive antenna lane with scout values supplied. Charging that positive-lane rate uniformly to the 2,775 requested antennas would add 4.85 CPU seconds as an illustration. Current proposals still need absolute timing and waveform checks. [Acquisition split](acquisition-split.md) · [Original stage clocks](first-55/stage-clocks.csv) · [Directed verifier measurement](directed-verifier.md)

The sparse solution, observed RF branches and two-slot ranking together recover too little held coverage to justify an additional waveform pass. These measurements use only the two saved detector packets. Five owned tests passed, covering metadata-only inputs, local support, signed alias transfer and scoring, and deduplicated stereo accounting. [Trial runner](sparse_rf_recall.py) · [Tests](../../../tests/pipeline_eval/test_sparse_rf_recall.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
trial_code="$PWD/reports/ALGO08/v3"
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$trial_code:$payload:$release/src:$release" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$trial_code/sparse_rf_recall.py" \
  "$case" "$new_first_pass" "$new_scores" \
  --signed-ceiling "$dense_metadata_scores" --visits-file "$new_visits"
```

Create the dense metadata gate receipt by running `DS30-0008` with three positional arguments. The signed comparison then accepts `DS30-0008` or `south-containing`.
