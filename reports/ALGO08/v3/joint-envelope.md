# Joint antenna timing from full-visit pilot envelopes

A blind joint timing sketch took **0.233 ms median CPU per stereo visit**. Its four hypotheses covered **2 of 80** dense DS30-0008 factor timings and **0 of 58** weak DS26 timings, even granting known signed CFO and a relaxed seven-sample timing enclosure. A mismatched-time control covered none. On the dense slice, every positive lane requires independent acquisition for at least one factor. A perfectly routed full stock fallback would project to **52.18 CPU s** for acquisition versus **58.96 s** for v3, even if signed carrier recovery and verification on successful short proposals were free. [Protocol](joint-envelope-protocol.md) · [Per-visit proposals and clocks](measurements/joint-envelope.json.gz)

## What the antennas share

The earlier receiver-lane audit found 28 distinct paired timing phases among 141 factors. It used a confirmed factor from one antenna to constrain the other. None of those pairs also had a signed CFO difference within 1 kHz. The present test computes directly from both raw lanes, so a signal can contribute even when its individual receiver does not verify it. The earlier differential scout computed within-frame complex lag products separately for each antenna. Frame covariance likewise compares repeated frames within each antenna. [Paired receiver audit](../single-core-2x/receiver-lanes.md) · [Independent differential scout](differential-fold.md) · [Frame covariance and layout](../single-core-2x/receiver-frame-planes.md)

The installed v3 factors on these authentic same-visit samples yield 11 distinct weak pairs and ten distinct dense pairs, whether the pairing allows two or seven wrapped samples. Their maximum timing differences were 0.572 and 0.610 samples, respectively. Their signed CFO differences in magnitude span 618–697 kHz on weak and 626–680 kHz on dense. At most 22/58 weak and 20/80 dense verified factors could be covered by transferring only such verified partner phases. Those counts cannot establish whether the other antenna contained a subthreshold contribution. The close timing and far-separated carriers support a joint phase-insensitive timing test while requiring independent signed carrier estimates. A direct complex cross-correlation of antenna streams estimates relative delay under suitable carrier compensation. Relative delay alone supplies no absolute pilot epoch in the repeated frame.

## Blind full-duration timing

Each of the 15 nominal frame origins contributes 3,333 four-sample energy cells, spanning the full 20 ms capture. Quarter-rate rounding leaves 20 native samples between these cells at origin boundaries. The statistic divides each antenna's cell energy by its own frame mean, caps it at eight and subtracts one. The synchronized arm averages the product of the two centered powers across the 15 origins. The cross-spectrum with the squared, centered pilot envelope then yields an absolute circular timing correlation. The mismatched arm applies the same computation after rotating RX1 by 1,111 coarse cells within each origin. It preserves every original RX1 cell energy and the same proposal budget. The marginal arm uses a separate matched envelope fold on each antenna. It offers four proposals per lane, like the other arms, with separate timing lists and two native sketch calls per stereo visit. [Native implementation](joint_envelope.c)

The reference uses complete signed scans. A hit requires one of the four blind timings within the tolerance of a stock factor on that antenna. The score excludes carrier reconstruction and exact-versus-rolled verification. It therefore measures what a perfect independent signed-frequency continuation of this timing shortlist could cover.

| Group, lane | v3 primary / residual | Joint hits at ±4 and ±7 samples | Mismatched hits at ±7 | Marginal hits at ±7 |
|---|---:|---:|---:|---:|
| Weak RX0 | 18 / 17 | 0 / 0 | 0 / 0 | 13 / 8 |
| Weak RX1 | 18 / 5 | 0 / 0 | 0 / 0 | 5 / 0 |
| Dense RX0 | 32 / 21 | 1 / 0 | 0 / 0 | 20 / 10 |
| Dense RX1 | 20 / 7 | 0 / 1 | 0 / 0 | 9 / 1 |

The joint and mismatched arms each send **176 proposals to 44 empty v3 lanes** in the dense slice. These are proposals that an independent gate would have to dismiss or verify. The saved factors establish disagreement with v3 and carry no independent satellite label. The physical inputs are the fixed enriched DS26 archive and the first 48 scheduled DS30-0008 visits, with all eight RF channels and both antennas.

The two planted same-epoch cases recovered both antennas at the top joint hypothesis, even with 1.146 MHz between signed CFOs and different antenna gains. On the planted separate-epoch cases the method covered one of four factors. It covered neither planted one-lane factor. The unmatched RX1 shift covered none of the planted factors. The marginal arm covered all ten planted factors. Both independent-noise visits produced four joint hypotheses and no stock factors. These spot checks establish what the common-envelope statistic can recognize and the burden it imposes on negative lanes.

## Independent residual work and the recording budget

Across five interleaved repeats the joint and mismatched sketches took 0.233 and 0.232 ms median CPU per dense stereo visit, and 0.241 and 0.240 ms on the aggregate mean. The complete stock pair took 5.663 ms median on the same visits. Marginal costs were 0.206 and 0.205 ms medians per call. FFT plans and pilot spectra were reused. All arms pay full signed input authentication outside these clocks.

At the generous timing tolerance, the joint list omitted 27 of 28 dense residual timings and all 22 weak residual timings. An earlier bounded experiment on the same physical slices measured the independent waveform work with original scout timings and CFOs supplied by an oracle. Its dense signed cancellation averaged **0.534 ms per triggered cancellation**, and its integer and fractional verifier averaged **0.726 ms per factor**, across both ranks. The strict whole candidate path averaged **1.69 ms per stereo visit**, including oracle knowledge of empty lanes. A guarded variant with oracle fractional time as well averaged 0.679 ms on each positive dense lane. All estimates exclude any cost to derive an independent signed carrier or reject these new false proposals. [Native verifier and cancellation measurements](directed-verifier.md)

The half-acquisition CPU budget is **1.16 ms per stereo callback** on DS30-0008, given the original 21.623 CPU s spent outside callbacks. The joint sketch costs 4.2% of matched dense native CPU. Retrying the 52 positive lanes with incomplete timing costs another 77.6%. Applying these ratios to the archived 37.338 CPU s callback total gives **52.18 CPU s** including outside work, or **1.13×** CPU speedup. The estimate grants free work on every other lane after the sketch, assumes the prefix lane mix transfers to the full recording, and prices retries using separately measured original lane clocks. It supplies no wall-clock or position result. An independent residual search designed specifically around a cheaper timing statistic would have a different cost model. [Complete installed acquisition split](acquisition-split.md)

The result rules out replacing independent acquisition with this common pilot envelope search on these slices. It leaves unmeasured other nonlinear cross-antenna statistics and a separate carrier-resolved joint search. Those routes would still need to recover one-lane and noncoincident evidence within the complete callback budget.

## Reproduce

The installed receiver is checked against `2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5`. The dense slice authenticates the touched member and raw lanes before comparison. The weak reader checks each indexed I/Q digest. The receipt records scoring inputs, pilot hashes, signed stock factors, proposal arrays, compiler, and native and wall clocks.

```bash
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 45s "$@"
}
lock sudo -n -u leo env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.joint_envelope_trial "$new_work" \
  /opt/leo-algo08/algo08v3/payload/receiver.so "$release/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json /srv/bulk > "$new_receipt"
lock env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$tree/.venv/bin/python" -BPs -m pytest -q \
  tests/pipeline_eval/test_joint_envelope.py tests/pipeline_eval/test_receiver_short_signed.py
```
