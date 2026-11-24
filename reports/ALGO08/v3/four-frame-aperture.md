# Four separated pilot frames in the original 20 ms visit

The four-frame schedule gives up one independent pilot observation and adds a wide time span that the current semicoherent verifier cannot turn into frequency precision. Its maximum paid opportunity is also too small to pass both field 2× gates. The desk gate stops here. No variant was built or measured, no member was enrolled, and the active five-frame receiver stayed unchanged.

## Source-derived schedule

The frozen receiver samples at 10 MHz. Its timing and delay scout uses a nominal 750 Hz cadence, a 13,333-integer-epoch search, an 88-sample pilot offset, 44 samples per symbol, and the original early and later-symbol gates. In a complete visit the largest set of origins that is valid under the latest confirmation for every integer epoch is 0–13. Among four distinct sorted origins symmetric about that scout's center, keep original parity at every selected slot and maximize the frame-centre second moment. The resulting diagnostic schedule is **0, 1, 12, 13** at samples **0, 13,333, 160,000, 173,333**. This rule uses only hardware constants. The earlier measured distributed schedule used eight origins and compared against a 12 ms primary. The earlier four-frame measurement used four contiguous origins inside 66,444 samples. [Earlier distributed receiver](distributed-aperture.md) · [Four-contiguous-frame test](four-frame-primary.md)

| Verified scout origins and ideal frame geometry | Active five contiguous | Four distributed | Earlier eight distributed |
| --- | ---: | ---: | ---: |
| Nominal frame-centre time from the first origin | 2.667 ms | 8.667 ms | 8.667 ms |
| Frame-centre variance | 3.556 ms² | 64.444 ms² | 36.000 ms² |
| Frame-origin information ratio if all frame phases were coherent | 1.000 | 14.500 | 16.200 |
| Equal-SNR information ratio with free phase per frame | 1.000 | 0.800 | 1.600 |
| Symbols contributing to one exact spectrum | 320 | 256 | 512 |
| Early confirmation group sizes | 3, 2 | 2, 2 | 2, 2, 2, 2 |
| First unused sample of latest confirmation | 79,777 | 199,777 | 199,777 |

The coherent information ratio uses the sum of squared centered origins with equal independent noise and an unknown common phase. Current verification instead sums powers of independent 64-symbol FFTs. Arbitrary per-frame phases cancel. With equal per-frame SNR and independent phase as a nuisance, the ideal local information uses the within-frame time variance and scales with the number of frames. Four instead of five implies 0.97 dB less information and 25% higher variance in this model. The half-pilot delay product likewise uses each fixed 1,408-sample local delay with nominal 7.102 kHz phase ambiguity. Additional separation of frame starts supplies no longer delay. The native residual grid stays at 443.892 Hz spacing and 227.273 kHz cyclic period from its 44-sample symbol cadence and 512 bins. The earlier centroid difference can shrink when measurements use the later window, but this does not restore the missing independent observation. [Centered chirp bound](within-aperture-chirp.md)

A coherent redesign would be separate. For a pair of comparable-frequency coherent tones, the ideal four-origin array response has 0.933 normalized power at a **62.5 Hz** separation, 0.750 at **125 Hz**, and almost unity at **750 Hz**, including hardware sample rounding. The five-frame coherent diagnostic has 0.557 and 0.040 at the first two of those offsets. A finer coherent main lobe comes with additional large sidelobes and the common frame-rate ambiguity. None of these sidelobe numbers describe the current verifier's per-frame response. The timing scout takes dominant modes of the frame covariance and scores short-template lags inside those modes. A constant phase on each row rotates the covariance eigenvectors and cancels under backprojection, up to mode degeneracy and numerical rounding. How a sparse array changes actual multi-carrier conditioning, dominant modes or losing peak order remains open.

The four slots preserve the physical even/odd normalization buckets. Confirmation still uses two disjoint early groups and two disjoint later groups, now using physical frames 0 and 12 versus 1 and 13. The source sums each group's per-frame powers and demands a zero residual winner against the other 63 bins in every group for the attempted gate. The two later symbol gates and early fallback observe the same selected frame list. They cannot independently verify a carrier confined to excluded middle frames. Every-eighth full two-scan anchors would still cover both radios on their original RF/channel/edge chronology, with no off-anchor confirmation beyond the selected visit. Uneven fading and multiple carriers could change both the seed and the winning signed factor. Prior contiguous four lost seven and four strong 8 ms counterparts on DS30-0008 and DS30-0169, respectively. Those are genuine findings for the contiguous shape. The spread design's factor losses remain unmeasured. [Signed support and paired results](four-frame-primary.md)

## Native load and exact dependencies

The last scout confirmation needs the largest original epoch plus the offset and 296 symbols after original frame 13. The unchanged contiguous loops would therefore convert and, if called at shifted center, mix up to 200,000 complex times per antenna in the timing source, compared with 80,000 today. A positive verifier reload would copy the same complete span into its native CI16 scratch. The raw reader still authenticates the entire stereo input under both recipes, including original compressed, decoded and per-visit commitments.

An exact selected-output stride-four FIR could reduce the **20,000** active output count to **16,152** on the four-frame variant, a saving of 19.2% against the active 8 ms tiled implementation. These are two whole-block intervals on row starts 22 and 40,022 with 81-tap input halos. Applying the same unused-output proof to five contiguous origins leaves **18,076** outputs, so the frame-list-only advantage under equal FIR pruning is **10.6%**. An even wider 50,000-output FIR negates the gain without pruning. The earlier eight-distributed run already implemented original-tile FIR pruning, obtained exact retained output bytes, and saved only 3.8–4.0% of its own native time. Its overall native costs still exceeded contiguous 12 ms. [Original FIR experiment](distributed-aperture.md)

The conservative full-rate input mask, including the original wrap padding and late confirmation, retains `[0,39793)` and `[159984,199793)`, or **79,602** time slots per antenna. That is only 398 fewer than the active contiguous 80,000-sample load. Paying the discontiguous read and mixer selectively would require preserving original absolute sample and FIR/SIMD origins, receiver parity, original fractional Lanczos and tap halos, and keeping the complete original CI16 source authentication. This desk mask is geometry, without a protected-page or byte-parity test of a four-frame implementation. It does not authorize discarding samples in the current live reader.

## Paid speed ceiling from the original field pairs

The frozen first-eight scorecard contains seven timed pairs, six where both builds reached publication. For each pair the reducer reads the bound successful successor receiver witness and takes only its exclusive `short_primary` CPU or wall clock. It optimistically subtracts that fraction from the corresponding through-exit time, keeps all paid acquisition, full anchors, routing, solver and output work fixed, and recomputes both summed and reciprocal median paired speedups. CPU and wall stay separate. The all-timed population retains the DS30-0397 installed failure and the successor completion, and the six-pair population omits that asymmetry. Neither version adds the unmeasured DS30-0452. [Frozen paired field clocks](first-eight-two-gate-budget.md)

| Timing population and hypothesis | Wall seconds removed | Wall summed / median | CPU summed / median |
| --- | ---: | ---: | ---: |
| All seven, actual archive | 0 | 1.609× / 1.497× | 1.541× / 1.497× |
| All seven, 12% off short native | 7.940 | 1.647× / 1.530× | 1.577× / 1.538× |
| All seven, 20% off short native | 13.233 | 1.673× / 1.552× | 1.603× / 1.566× |
| All seven, entire short native free | 66.163 | 1.992× / 1.903× | 1.908× / 1.923× |
| Both terminal six, actual archive | 0 | 1.638× / 1.574× | 1.593× / 1.566× |
| Both terminal six, 12% off short native | 6.278 | 1.676× / 1.612× | 1.630× / 1.607× |
| Both terminal six, entire short native free | 52.314 | 2.010× / 1.966× | 1.962× / 1.989× |

Twelve percent rounds up the strongest historical contiguous-four short CPU improvement (range 6.0–11.7%). Twenty percent is a favorable frame-linear scenario even though several stages have fixed work, and is presented as a sensitivity rather than a kernel upper bound. The absolute paid short-native scope is the entire exclusive short stage. Freeing that scope would still save less than the seven-pair summed wall deficit of **67.253 s**. Across all seven, the median wall gate alone requires **35.3%** of short time for 1.6×. The six both-terminal subset would reach both 1.6× gates with **8.3%** wall and **10.1%** CPU savings from that scope, assuming no other stage moves. No short-only scenario passes both 2× gates in either population. A faster overall solve after a change of detections or a dedicated different raw format lies outside these bounds.

Existing contiguous-four runs saved only **5.55–8.56 ms** of native CPU per member. Complete acquisition ranged from a 17.083 ms CPU saving to a 13.023 ms loss, and every whole worker exit took longer. The extended readback, lower ideal information and prior support failures make a four-distributed member trial a poor next test for the speed or accuracy gap. There is no proposed runtime change. [Prior genuine four-frame timings](four-frame-primary.md)

## Reproduce the desk audit

Run `python -B reports/ALGO08/v3/four_frame_aperture.py /srv/postgres-nvme/leo-ds30-evaluation-20261124` with local receipt access. It binds the six native source snapshots, campaign rows, raw authority and receiver result/witness hashes, short library SHA, archived member receipts, and first-eight scoring scope. Four component tests passed. The portable gzip receipt SHA-256 is `dea5f711a6912897c1ab0080f74b7f4bb4bba291461719f70473de9c29cfdf49`. [Machine receipt](measurements/four-frame-aperture.json.gz) · [Reducer](four_frame_aperture.py) · [Tests](../../../tests/pipeline_eval/test_four_frame_aperture.py)
