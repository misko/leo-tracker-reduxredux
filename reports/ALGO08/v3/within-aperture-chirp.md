# Within-aperture Doppler drift on two physical DS30 pairs

The saved measurements give little reason to add a chirp bank or a dwell-derived uncertainty term. After subtracting the linear centroid term, matched signed carrier-frequency offset (CFO) differences remained at **111.82 Hz RMS on DS30-0220** and **97.12 Hz on DS30-0274**. The two captures' fitted local frequency curvature could move the difference between the aperture means by at most **0.0031 Hz** and **0.0050 Hz** on those measured rows. The estimated pure-chirp distortion of a short isolated pilot spectrum was below **0.000023** in normalized power on every qualified row. Abrupt, competing peaks remain an open receiver problem.

## Qualification and measured scale

DS30-0220 was the newest eligible completed original field pair with at least 6,000 visits when the protocol froze. DS30-0274 is a second original capture. Installed full 20 ms and sparse 20/8 ms packets bind the same source authority, complete issued chronology, channel/RF/radio, exclusions and offered region within each capture. The sparse route emitted its unfiltered native factors with no later remeasurement. The comparison used neither surveyed positions nor fitted orbit curves. DS30-0049 and the separate DS30-0086 timestamp experiment stayed outside the readout. [Frozen protocol](within-aperture-chirp-protocol.md)

| Original measurement | DS30-0220 | DS30-0274 |
| --- | ---: | ---: |
| Issued visits | 6,767 | 6,772 |
| Evaluated short lanes | 8,704 | 11,830 |
| Both positive | 2,426 | 4,778 |
| Installed-only / sparse-only / both empty | 790 / 734 / 4,754 | 939 / 927 / 5,186 |
| Both positive within 250 signed Hz and two absolute samples | 1,892 | 3,954 |
| Same-atom rows inside an installed Graph piece across both apertures | 1,747 | 3,611 |
| Absolute local slope P95, Hz/s | 4,417 | 4,154 |
| RMS of linear centroid term, Hz | 22.45 | 21.86 |
| Signed paired CFO RMS before / after subtracting that term, Hz | 111.47 / 111.82 | 98.57 / 97.12 |
| Maximum remaining curvature bias between the means, Hz | 0.00305 | 0.00500 |
| Conditional uniform-time frequency spread, RMS across rows, Hz | 20.57 | 20.04 |
| Post-centroid differences exceeding even local combined instantaneous support | 1,282 / 1,747 (73.4%) | 2,465 / 3,611 (68.3%) |
| Alias-folded absolute differences beyond one native residual bin, all paired positives | 324 | 572 |
| Alias-folded absolute differences above 10 kHz, all paired positives | 273 | 515 |
| Full anchors with identical winning typed rows / both positive | 444 / 470 | 777 / 805 |

The same-atom test uses a signed CFO difference and the actual absolute fractional epoch inside the original visit. Alias-folded counts are a separate diagnostic. A full anchor has the same aperture on both sides, yet some winner rows differ and the candidate has 70 and 86 additional positive anchors across the two captures. Those anchors control for aperture geometry while exposing unequal temporal selection. The signed variance comparison is conditional on the strict matches. Seventy-four and 129 such rows had no usable installed Graph piece, while a further 71 and 214 were at a piece edge. All are retained in the packet counts.

## Aperture and bound

The pinned receiver forms a 128-point FFT on each 64-symbol pilot, sums powers and interpolates the summed spectrum to a 512-bin cyclic residual grid. A constant frame phase cancels in its exact and rolled spectra. The nominal residual spacing is **443.892 Hz**, the cyclic period **227,272.727 Hz**, and the ideal pilot first null is about **3,551 Hz**. To pass the gate, the difference between the best normalized exact and rolled powers must reach the 0.025 threshold. The equivalent relative-phase arithmetic still computes each of those same semicoherent spectra. The scout has its own fixed half-pilot delay product with five short or fourteen full frames. The verifier may use a fifteenth full frame. Its fractional-epoch frame admission follows the original interpolation halo.

For the isolated equal-power model let $X$ be verified frame-centre time measured from the mean and let $U,V$ be independent uniform symbol times measured from a pilot's centre. A signed linear chirp with slope $a$ contributes the phase difference $A=2\pi a X(U-V)+\pi a(U^2-V^2)$. Averaging the linear term gives zero by the centred frames and symmetry of $(U,V)\mapsto(-V,-U)$ at fixed $U-V$. The normalized power difference at any fixed residual frequency is thus bounded by $E[A^2]/2=4\pi^2a^2\operatorname{Var}(X)\operatorname{Var}(U)+\pi^2a^2\operatorname{Var}(U^2)$. On the short aperture, the bound at the two observed slope distributions' P95 was $1.81\times10^{-5}$ and $1.60\times10^{-5}$. The full-aperture bounds at P95 were $1.64\times10^{-4}$ and $1.48\times10^{-4}$. These are power bounds for one isolated ideal carrier at a fixed timing, so a direct comparison to the 0.025 margin conveys scale only. The bound can certify unchanged bin ordering in the model when the best-to-runner-up score gap exceeds twice the power bound, but the saved typed rows lack the gap and losing scores for a real certification.

Even at the declared Graph stress rate of **8,000 Hz/s**, an isolated smooth carrier spans 44.92 Hz over the five verified pilots and 151.59 Hz over fifteen. The centered radii of the two apertures sum to 98.25 Hz in frequency, and the entire 20 ms acquisition spans at most 160 Hz under that slope condition. The normalized uniform-power perturbation is at most $5.94\times10^{-5}$ on the short aperture and $5.54\times10^{-4}$ on full. The scout's phase spread across its delay products is about 0.038 rad short and 0.123 rad full at the same rate. The unequal-symbol-weight phase-arc allowance is looser at this stress rate, up to 0.038 and 0.132 in normalized power for fixed magnitudes. It gives no blanket decision certificate. The true tap amplitudes, oscillator transients, changed cancellation and ranking branches, and exact or rolled mixtures are outside the uniform-pilot model.

The mean-curvature bound uses the actual installed Graph piece's analytic second derivative and the recorded frame times. For each exposure it is at most $\sup |f''|\operatorname{Var}(t)/2$ about its fractional equal-frame centroid. This is conditional on the empirical signed track being the local frequency trajectory. The uniform-time spread describes sampling an instant within a deterministic exposure. Adding it as independent observation variance would assume an uncertainty process absent from the source and the saved measurement.

The independent DS30-0163 visit 61 witness is separated by **117,998.563 Hz signed**, **109,274.164 Hz folded**, and **858.189 timing samples**. Its observed full-window local exact-minus-rolled score maxima were **0.083589** at the installed neighborhood and **0.000278** at the sparse neighborhood. The short estimate had cleared the gate at **0.025705**. This separation exceeds even the conditional 160 Hz stress excursion by over 680×. Those two neighborhoods also began from separate scout seeds. Direct within-aperture drift cannot transport one physical carrier between them under the modeled slope. A small drift could still change which competing branch wins near a tie. The separately scored neighborhoods do not identify the true satellite. [Original 0163 peak neighborhood](0163-signed-peak-neighbourhood.md)

## Work and decision

The measured exclusive native means were **1.192 / 1.062 ms** per short lane and **3.648 / 3.926 ms** per full anchor on DS30-0220/0274 respectively. A verifier-only correction would touch 320 short-aperture symbols for one fixed timing and each of the exact and rolled spectra. Rephasing before despreading would touch 14,080 original pilot samples at that timing. Evaluating three slopes at an otherwise fixed timing would triple the number of chirp-specific spectrum evaluations without sharing them. Each spectrum presently has five 128-point pilot transforms, one 128-point power-to-lag transform and one 512-point interpolation. Neither a per-symbol correction's wall cost nor an alternate scout's performance was measured.

Do not add a chirp bank or random dwell-based uncertainty from these results. A future ambiguity test would need the actual short exact/rolled surface and temporal frame support for two independently nominated peaks to separate carrier drift, coexistence and branch sensitivity. This readout reconstructed only the original saved Graph track preparation on the two bound packets. It used no raw waveforms, TLE propagation, survey joins, new fit, calibrated position or timed worker. A separate timestamp-only trial addresses the linear centroid term. [Earlier centroid work](sparse8-cfo-epoch.md)

Run `python -B reports/ALGO08/v3/within_aperture_chirp_readout.py` with the pinned release interpreter and release `src` and root on `PYTHONPATH`. The run requires read access to the original local result receipts and typed packets on NVMe and to the six code snapshots pinned in the readout. The two roles were separate original leases. The code and tests were sealed at `b192927c4` before either readout. The machine receipt is gzip SHA-256 `f3cf9159c27e3e513c32ea06df88327a28fcf20c4cfe7c7cc389e4d983e2645a`. [Sealed machine receipt](measurements/within-aperture-chirp.json.gz)
