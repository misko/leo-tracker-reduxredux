# Training-duration selection does not resolve DS6 accuracy

Keeping only tracks with at least 30 seconds of training span does not reliably improve the four pre-existing development scans. Two geographic errors improve and two worsen; none is below 1 km. Conditional held-out prediction on all original tracks worsens in every scan. This selection rule is not adopted.

| MS/s | Tracks retained / original | Baseline error (m) | Long-track error (m) | All-track held log-score change |
|---|---:|---:|---:|---:|
| 10 | 9 / 32 | 4925 | 5040 | -16.049 |
| 2.5 | 22 / 61 | 3643 | 2054 | -23.754 |
| 5 | 14 / 64 | 8502 | 8221 | -5.579 |
| 7.5 | 19 / 64 | 465 | 1942 | -49.677 |

Eligibility uses the interval between the first and last training observations only. Held-out support cannot make a track eligible. The interval is not continuous observation duration. A preliminary support inventory found no development track with 60 seconds of training span; the fixed 30-second rule retained at least nine tracks per scan. No geographic error was used to set eligibility or choose individual retained tracks.

The model, candidate lists, causal elements, stationary offset profiler, Student-t4 scale, randomized whole-visit masks, and local bounds are inherited unchanged from the corrected baseline. Three starts use the baseline horizontal position with baseline, -2 s, and +2 s timing. Selection uses retained-track training likelihood. All 12 starts converged and all selected positions remain inside the bounds.

After position selection, all original tracks are evaluated with exact propagated states. Their offsets are profiled on their own training visits at the frozen selected location. Omitted tracks cannot affect geographic fitting, but their held visits remain included in the reported predictive comparison. This is conditional prediction of trajectory shape, not prediction of absolute unknown transmitter frequency. Ground truth is read only by the post-fit summarizer.

Three tests cover training-only duration eligibility, exact retained track sets, frozen dependencies, complete three-start fits, training winner selection, exact propagation and stationary offsets, complete predictive accounting, and result/reference hashes. The experiment is local, uses inherited candidate shortlists and reused development data, and does not establish a universal optimal duration policy.

The 2.5 MS/s improvement to 2054 m is insufficient to justify adopting the cutoff selectively. The 7.5 MS/s result loses its previous sub-kilometre accuracy. The verified estimator remains unchanged: 6/43 independent scans below 1 km, and 754.938 m for the separately validated combined static-site estimate.
