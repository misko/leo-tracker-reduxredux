# One initial satellite assignment

Run two replacements for the initial assignment of compact v5. Both run the same downstream conservative recovery, orbit-history prior, signed correction and cavity decision as the compact projector. Publish both calibration arms. Both start with the complete recorded detector output, acquisition-time orbital catalogue, original clocks, and original 25 km tile.

* **First ranked branch** generates the original four calibration starts and four corner proposals, removes duplicates in their original order, and ranks them by the existing center residual. Refine only the first branch, with the original five refreshes and 48-iteration limit.
* **Single center seed** starts discovery at the supplied center with zero receiver calibration, runs its two ordinary discovery updates, then refines that one association. It omits the alternate seed and corner searches and the branch ranking.

The reference initial search refreshes up to three distinct branches and selects the minimum zero-calibration loss. Both replacements choose a single common assignment before the two calibration arms proceed. No thresholds or priors are fitted to the recordings.

Use the existing six timing recordings, DS26-0036, DS26-0122, DS26-0237, DS29-0082, DS29-0174 and DS29-0247. Preserve all attempts, including failures. Run the two replacements and a matched compact-projector control on the same host CPU per recording, with one numerical thread and a ten-minute per-run deadline. Rotate the run order over the roster. Keep inference outputs separate from the truth-based scoring step. Compare fix count, published errors, matched per-record errors, conditional RF RMS and measured initial/whole wall time. A 10% accuracy claim requires full fix coverage and both median and P95 no greater than 1.10 times their respective full-v5 baselines on each dataset.

On the larger 135-recording panel inspect the authenticated original checkpoints to count when the first-ranked branch won. A mismatch is a search disagreement and requires a new fit to establish its downstream effect. A wide-panel position distribution needs an actual or demonstrably identical downstream input for every included result. Keep this diagnostic separate from directly measured position distributions. No new RF acquisition takes place.
