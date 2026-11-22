# Can the history rule out today's continuation before measuring CFO?

The three-donor history certificate displaced **zero native calls** at the existing 64-lane FIFO budget. All **3,826 published probe rows** and **896 selections** matched the released continuation and the existing deferred planner. The proof is retained as an offline experiment. [Paired ledger replay](deferred-history-bound-results.json)

## Certificate

The released vote requires three distinct earlier visits from the same receiver, channel and RF. A line through the current frequency has slope within ±8,000 Hz/s. Each agreeing donor can be within 800 Hz of that line. At least one agreeing donor must be 0.4 s old relative to the current visit. Only positive hardware-counter ages up to eight seconds qualify, within the existing twelve-slot history. [Released votes](../../../tools/pipeline_eval/variants/carrier_continuation.py) · [Existing deferred planner](deferred-continuation.md)

For known donor frequencies \(f_i,f_j\) and separation \(d>0\), a supporting slope must lie in \([(f_j-f_i-E)/d,(f_j-f_i+E)/d]\), with \(E=1600+2^{-10}\) Hz. Intersect the interval with the original slope range. Each pair comes from two different visits. A visit with two carriers still provides at most one vote, and a triple chooses one candidate from each visit before checking all three pairs.

| Unresolved eligible donors | Necessary condition after the available count and age pass |
| ---: | --- |
| 0 | Three distinct known visits with a common intersection across all three pair intervals. The oldest of the three must satisfy the age gate. |
| 1 | Two compatible known visits, with an old-enough known visit or an old-enough unknown. Any feasible all-known triple already contains such a known pair. |
| 2 | The unknowns can both agree with one known donor on a constant line. An old-enough known or unknown donor completes the age condition. |
| 3 or more | Three unknowns can agree on a constant line. If only a known donor is old enough, it can join two unknowns. |

The pair screen is a necessary condition for the original seed and voting procedure. An inconclusive result follows the existing receiver and selection path. A negative result keeps the window pending, so a later visit can still request both of its independently verified factors. FIFO and the one-call-per-lane rule continue to apply. [Bound implementation](../../../tools/pipeline_eval/variants/experimental/continuation_history_bound.py)

For the checked numerical domain, known frequencies have magnitude at most \(2^{30}\) Hz. An agreeing prediction therefore has magnitude below \(2^{31}\) Hz and the binary64 subtraction that produced it has error below \(2^{-20}\) Hz. For an age up to eight seconds, each delay conversion contributes less than \(2^{-49}\) s, and the slope product contributes less than \(2^{-36}\) Hz of rounding. Rounding the 800 Hz residual contributes less than \(2^{-42}\) Hz. The pair frequency subtraction and computations of the two numerator endpoints also each round by less than \(2^{-20}\) Hz for a compatible pair. The extra \(2^{-10}\) Hz encloses the sum of these errors and the pair time conversion. Divided endpoints are rounded outwards. Integer counter differences encode the 0.4 s threshold at exactly 4,000,000 ticks. Frequencies outside the checked domain keep the ordinary measurement path.

## Ledger replay

Seven repeats alternate planner order and add the recorded native CPU of each requested lane. The ledger and existing saved detection file bind the same raw authority. The replay checks each ordered probe against the released continuation and each planner, checking both candidate identity and fields. The measured CPU covers the planner and replay bookkeeping. Native times are charged from the original frozen-detector ledger.

| Saved recording | FIFO lanes | Native calls, current → certificate | Native CPU saved | Extra planner CPU, median | Net estimated saving |
| --- | ---: | ---: | ---: | ---: | ---: |
| Physical DS30-0016 | 16 | 1,373 → 1,373 | 4.52 ms | 2.52 ms | 2.00 ms |
| Physical DS30-0016 | 64 | 1,357 → 1,357 | 0 | 2.50 ms | −2.50 ms |
| Physical DS30-0016 | 192 | 1,357 → 1,357 | 0 | 2.43 ms | −2.43 ms |
| Southern simulation | 16 | 2,384 → 2,384 | 0 | 0.76 ms | −0.76 ms |
| Southern simulation | 64 | 1,327 → 1,327 | 0 | 0.84 ms | −0.84 ms |
| Southern simulation | 192 | 1,327 → 1,327 | 0 | 0.85 ms | −0.85 ms |

At 64 lanes, the physical certificate tested 902 fully known histories and 52 with one unknown. It deferred six foreground calls, all of which were later needed as donors. The complete queried index set and **4.492829 native CPU seconds** were identical. The southern trial found a compatible pair or triple in all 499 histories where it could test the frequency bound. Another 733 histories had at least two unknown donors and necessarily remained open. The southern queried index set and **4.319399 native CPU seconds** were identical. The 16-lane physical run replaced 15 requests with 15 different requests as the FIFO filled. The smaller budget still charged more native CPU than the 64-lane planner.

## Reproduce

The trial reads existing factor ledgers and detections. It applies the certificate only inside the offline replay. Component tests cover zero through three unknown donors, multiple frequencies in one visit, contradictory pair intervals, the slope and residual boundaries with large hardware counters, and a deferred visit later queried as a donor. All 26 targeted tests passed.

~~~bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_pairs="$algo08_work/integration-shared/pairs"

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:. timeout 80s "$@"
}
algo08_lock "$algo08_python" reports/ALGO08/single-core-2x/deferred_history_bound_trial.py \
  --case DS30-0016 "$algo08_work/ledger-DS30-0016.json.gz" \
    "$algo08_pairs"/DS30-0016/candidate/fast-scan-automatic-work/*/detections.json \
  --case south "$algo08_work/ledger-south.json.gz" \
    "$algo08_pairs"/south/candidate/fast-scan-automatic-work/*/detections.json \
  --pending 16 64 192 --repeats 7
algo08_lock "$algo08_python" -m pytest -q \
  tests/pipeline_eval/test_continuation_history_bound.py \
  tests/pipeline_eval/test_deferred_continuation.py
~~~
