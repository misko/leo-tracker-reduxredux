# The timing scout's sample-rate floor

The frozen ALGO08v2 scout already decimates complex 10 MS/s I/Q to **2.5 MS/s**. Another factor of two would reduce the passband to ±625 kHz and fold distinct parts of the **±800 kHz signed carrier search** onto the same scout bins. The pinned pilot on either edge is already wider than 1.25 MHz before any carrier offset. A single lower-rate stream therefore cannot preserve the quarter-rate scout's signal support. This rate change was stopped at the physics and asset measurement. [Numerical receipt](receiver-rate-results.json)

Both pilot edges use eight coded subcarriers spaced 234.375 kHz, with outer centers at ±820.3125 kHz and 1.640625 MHz between them. Across all allowed CFO, the union of shifted tone centers extends to ±1.6203125 MHz. The frozen quarter-rate FIR already attenuates outer pilot energy at the ends of the allowed band. The comparison below measures the additional effect of another factor of two on the actual pinned scout input. [Pilot frequency definition](../../../src/leo/analysis/starlink/templates.py) · [Frozen receiver source](../../../native/algo08v2/tools/pipeline_eval/variants/timing_first_receiver.c)

## Retained support

The measured signal was the first 128 scout pilot symbols from each pinned 10 MS/s edge asset. The script shifted each by fixed signed frequencies and compared the released 81-tap quarter-rate FIR with a 161-tap eighth-rate FIR from the same Kaiser design family. The ideal column gives the fraction of quarter-rate-filtered energy an ideal ±625 kHz cut retains. The proposed FIR column uses the same quarter-rate energy as its denominator. Values combine both signs where shown and both pilot edges.

| Absolute signed CFO | Shifted tone centers inside ±625 kHz | Centers also supported by the unshifted eighth-rate reference | Ideal retained energy | Proposed FIR retained energy |
| --- | ---: | ---: | ---: | ---: |
| 0 kHz | 6/8 | 6/8 | 66.6–68.0% | 63.9–65.0% |
| 400 kHz | 5/8 | 4/8 | 65.5–67.6% | 64.2–65.8% |
| 625 kHz | 4/8 | 3/8 | 60.5–62.2% | 59.4–60.5% |
| 800 kHz | 3/8 | 2/8 | 55.8–57.5% | 54.0–55.5% |

The retained energy can still contain a real pilot. It is weaker, and the band edge sees a different set of coded subcarriers from those retained in a centered nominal template. An alias-tolerant hypothesis search could still be designed and qualified. The energy fractions alone give no guarantee that it would nominate the same weak or overlapping carriers on each lane.

At 1.25 MS/s the legal interval −800 to −450 kHz folds onto the same discrete frequencies as +450 to +800 kHz. These overlaps occupy 350 kHz of folded bandwidth, or 28% of the 1.25 MHz spectrum. The existing ±4-sample native refinement can cover the nearest point on an eight-sample phase grid. That leaves roughly 1,667 independent timing bins per frame, down from 3,333, and still requires the correct timing region to survive nomination. Native refinement can distinguish aliased CFO hypotheses only when they reach its shortlist. Putting both signed branches into refinement can also increase its cost.

## Cost bound

With the same filter design, halving the output sample count while doubling the FIR taps leaves approximately the same arithmetic in the front-end filter. Carrying two independent half-rate phases or channels to retain quarter-rate information likewise preserves aggregate sample throughput. Splitting a length-4,800 timing transform into two length-2,400 transforms offers about 8% less arithmetic in an idealized FFT count. The frozen timing-search stage is about 11% of native receiver CPU, so this transform split alone projects about 1% total native savings before channel recombination, extra proposals, or any exact fallback. These are work estimates, not measured alternate receiver times. [Frozen whole receiver profile](receiver.md)

The next independent idea would need either channelized pilot-specific hypothesis generation or a certified polyphase computation of the existing timing score. Neither is the proposed single-stream downshift. The full-window receiver and lane-specific verification remain frozen. This measurement used no archived I/Q, geographic coordinates or solver outcomes.

## Reproduce

```bash
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 timeout 80s \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python \
  reports/ALGO08/single-core-2x/receiver_rate_bound.py /opt/leo-algo08/current/assets
```
