# Independent linear pilot holdouts miss the dense acquisition budget

The new joint delay and signed-carrier shortlist reached **7 of 21 dense short positives** and **6 of 34 weak short positives** when either view could supply the answer. Both independent views reached only **3 positives per cohort**. The favorable dense model grants all empty timing and carrier searches for free, along with all candidate work. It still saves only **3.092 CPU s** against the conditional **3.490 s** target. The assay reached the frozen stopping rule. [Protocol](joint-pilot-holdout-protocol.md) · [Signed trace and calculations](measurements/joint-pilot-holdout.json.gz)

## What was measured

Two 4 ms native CI16 views came from `[0, 40000)` and `[80000, 120000)`. They used negative and nonnegative digital receive bins, respectively, without a shared input sample. At each of 6,401 signed frequencies from −800 to +800 kHz, a view retains the sixteen strongest lines of the shipped synthesis pilot in its own receive band. The frequency ranking uses the sum-of-magnitudes upper bound for its coherent line sum. Each view keeps eight frequency tiles and searches circular delay from the complex line phases only within those tiles. It keeps four delay peaks per tile. This gives every factor up to 32 chances per view, at the generous tolerance of **±7 samples and ±4.55 kHz**. The plan uses only the original lane, digital tuning and fixed pilot. [Assay implementation](joint_pilot_holdout.py)

The assay uses FFTs to obtain the exact finite-block line projections and sparse delay synthesis. Those calculations establish the shortlist coverage of this fixed representation. The cost model grants these calculations for free. Direct evaluation of the prescribed grid would have 204,832 line terms and 853,504 complex delay terms per scan before accounting for how a real implementation obtains the input line coefficients. These are term counts for direct evaluation. The selected lines retain **1.78–3.71%** of shipped pilot power across the two edges and signed cells. The existing directed receiver had access to supplied timing and frequency. This assay generates its own blind joint tiles. [Previous directed verifier](directed-verifier.md) · [Fixed rank ceiling](shared-ambiguity.md)

The sealed input comprised 24 dense DS30-0008 stereo visits from its existing authenticated first member and 18 weak DS26 stereo clips from the staged archive. The installed full and released short factors matched their published controls by IQ digest, pilot edge, visit and antenna. The dense short scope uses the original schedule. The weak short scope forces its established 12 ms challenge. Reached 20 ms residuals use actual signed, quantized CI16 subtraction. The two views of a residual share conditioning on the original primary that was subtracted. The assay timed 0.954 s CPU on dense and 0.897 s on weak, including the original native reference calls, cancellation and oracle projections. Those times describe the assay.

| Cohort and scan | Verified factors | Either view | Both views | Nearest true carrier given for free, either view | Earlier cyclic carrier plus marginal timing, either aperture |
|---|---:|---:|---:|---:|---:|
| Dense scheduled short | 21 | 7 | 3 | 7 | — |
| Weak forced short | 34 | 6 | 3 | 8 | — |
| Dense 20 ms primary | 33 | 7 | 3 | 7 | 1 |
| Dense 20 ms residual | 21 | 3 | 1 | 4 | 0 |
| Weak 20 ms primary | 36 | 6 | 3 | 10 | 0 |
| Weak 20 ms residual | 22 | 1 | 0 | 6 | 0 |

The earlier comparison grants either of two cyclic apertures and the same antenna's marginal timing list, including raw timing supplied to residuals, at the same generous tolerance. The new coherent line score improves those specific proposal counts. Its nearest-true-carrier control fixes the original signed frequency to the nearest 250 Hz cell before ranking delay. Even that favorable control covers only 7/21 dense and 8/34 weak short positives. The control leaves other frequency-dependent rank effects outside its claim. [Earlier cyclic carrier](cyclic-carrier.md) · [Marginal timing and stereo controls](joint-envelope.md)

Both views emitted tiles on all **11 dense and two weak short empty lanes**. None of those empty lanes had an intersecting pair of tiles across the two views. Requiring a matched tile pair would also discard **18/21 dense and 31/34 weak short positives**. Two of twelve empty dense residual scans admitted an intersecting pair. These are proposal disagreements or agreement on receiver-defined empty scans. A usable empty decision still needs exclusion of unseen tiles under the original gate. The old cyclic presence statistic could skip only one of the same eleven dense short empties without losing a positive, and neither weak empty. [Archived empty-lane controls](cyclic-presence.md)

## Break-even

The measured dense short-stage model allocates **2.222 CPU s** to timing and carrier on empty lanes and **2.609 s** on positive lanes. At zero cue and confirmation cost, routing every empty away and applying the measured 7/21 positive coverage yields **3.092 s** of projected savings. Requiring the observed both-view support gives **2.595 s** under the same empty grant. Clearing 3.490 s would require rescuing **48.6% of positives at zero cost**, or **84.9% at 80 µs per issued short lane**, with every empty still free. The favorable bound also grants exact local confirmation on every hit and pays the original grid only for misses. The data support retiring this fixed 16-line rank and shortlist. A different representation would need its own coverage and cost evidence. [Measured short-primary stage profile](short-primary-fusion-profile.md) · [Conditional dense budget](warm-recording-budget.md)

Four component tests passed, covering signed delay and frequency, circular wrap, view isolation, empty agreement and cost accounting. The receipt's uncompressed SHA-256 is `cf8cd8531e12f1bb277b95324ee40e6c5a377323afb5112c5b218cb26503000d`.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
  TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$release/src:$release" \
  timeout 90s "$release/venv/bin/python" -Bsm reports.ALGO08.v3.joint_pilot_holdout \
  /dev/shm/leo-v3-joint-pilot-holdout-reproduction
```
