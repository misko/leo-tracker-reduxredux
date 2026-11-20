# Independent synthetic control for global GLRT receivers

Generate four 300 s synthetic acquisitions with coordinates drawn uniformly
within ±5° of fixed centers in Europe, Australia, Mexico and southern Africa.
Use the byte-identical Starlink snapshot archived on 2026-11-14 at 05:37 UTC
and stamp each acquisition after its receipt. The same TLE generates signals
and supplies the catalogue for inference. This isolates receiver search and
decision logic from post-TLE orbit error. No roof coordinates, prepared tracks,
source satellite IDs, membership tables or raw radio enter inference.

In each 50 s block independently choose two new catalogue objects with
elevation above 25° at five evenly spaced times over a 44 s activity window.
Assign each a fixed RF channel. Simulate the two receiver lanes on a sweep of
eight 250 MHz-spaced channels, with 20 ms valid probes, 24 ms visit cadence and
10 MS/s nominal sample rate. Four RF channels carry coherent candidates.
Report the sparse candidate lists at each probe without track links. Occasional
weak peaks and random missed observations add modest ambiguity.
Encode elapsed time only in the valid-start sample counter. The within-visit
probe offset is zero, matching all 13,530 actual DS26-0036 probes. Verify the
first and last scheduled probes against the native observation adapter on an
unscored test before drawing the corrected packet.

Solve light time between the transmitter at emission and the Earth-rotating
receiver at reception. Report a 750 Hz frame epoch from one emitted frame's
sample-counter displacement modulo the nominal frame period. Compute received
CFO as minus carrier frequency times retarded range rate divided by the
speed of light. Add orbit-specific constant carrier offsets and transmit phase,
a common sample-clock bias up to 4 ms and ±0.4 ppm rate error, independent
receiver LO biases up to 5 kHz and drift, a shared RF slope within
±3,500 Hz/GHz, 24 Hz carrier noise and 0.12 sample epoch noise. Report the CFO
modulo the 4.4 µs pilot ambiguity. The optimistic control has at most one
strong emitter per RF visit, near-Gaussian jitter, ideal reference epochs
apart from the injected terms, and no unmodeled ionosphere, beam changes,
detector search error, real waveform interactions or range ambiguity failures.

The negative control shuffles complete candidate lists between occupied
visits of the same receiver and RF in the first acquisition. It preserves the
scan cadence, pairwise frequency/epoch values, occupancy and score marginals
while destroying persistent emitter timing. It has no defined receiver position.

Use the frozen global solver releases with no site or tile prior. Seal their
source bytes before generating a random 32-byte seed and the four anonymous
captures. Keep the seed, identities and coordinate labels separate until the
global predictions seal. Attempt all four positives and the shuffle for
point-pair votes, rate triplets and folded Doppler on the same fresh packet.
Set a 150 s per-case bound and pin seven single-thread workers to CPUs 8–14.
Retain timeouts and invalid inputs in the attempt denominators.
Score both zero and fitted calibration
arms against the sealed position and report conditional frequency fits
separately. No parameters may be adjusted from this panel.
