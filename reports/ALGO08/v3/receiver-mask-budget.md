# How many short receiver calls could pay for half-time?

For the first four fixed DS30 assignments, the projected fraction of short-lane CPU that must disappear is **36.58%** when priced at the measured dense rate and **37.78%** at the measured weak rate. For the first sixteen the corresponding figures are **23.84% and 24.63%**. A policy that skips one radio on three quarters of the short visits skips about **37.5%** of short calls. That leaves very little room on the first four for making the decision, rerunning the solver, or waiting for storage. The figures below are model sensitivities. Actual savings depend on which calls are skipped, how the resulting positions change, and what the full process does. [Calculation](receiver_mask_budget.py) · [Input pins, admission counts and complete results](measurements/receiver-mask-budget.json)

The original full-length assignments have similar issued counts and different numbers of usable visits. Among the first four, only **4,644 of 6,770** stereo visits on DS30-0374 were admitted, compared with **6,765 of 6,772** on DS30-0008. The dense raw replay measured **12.6353 CPU s for 11,834 short calls**, or **1.068 ms/call**, with another 1,696 full calls. The weak recording’s mean was **1.034 ms/call**. Both radios, all original compressed and decoded authentication, and the full anchors remain charged. The model uses the dense observed call count directly for DS30-0008. On the other recordings it optimistically pools streams before rounding up the number of anchors. Every real stream starts with its own anchor, so short calls can only be fewer than this count. [Measured dense acquisition](dense-full-short-raw.md) · [Weak receiver clocks](quiet-cycle.md)

| Short-call CPU removed at the dense price | First 4 median / summed time ratio | First 16 median / summed time ratio |
|---:|---:|---:|
| 25% | 0.5143 / 0.4963 | 0.4880 / 0.4988 |
| 37.5% | 0.4989 / 0.4822 | 0.4748 / 0.4863 |
| 50% | 0.4835 / 0.4682 | 0.4616 / 0.4738 |

Starting with the previously frozen model at **252.51 compressed MB/s** and zero exposed wait, subtract the per-recording eligible lane count times the mean call CPU and the skipped fraction. Existing solver, common and publication charges stay fixed. Each completed case is matched to its own v3 elapsed time. The unsplit DS30-0022 failure retains its entire original charge on the sixteen-case panel. With the weak call price, 37.5% deletion gives **0.5003 / 0.4836** on the first four. Actual per-lane costs, remaining branches and storage service can vary. No measured CPU is removed by dropping an invalid visit that never called the receiver. [Original case-wise model](roster-savings.md)

| Additional elapsed cost per adjustable recording | Short-call fraction needed on first 4, dense price | Fraction needed on first 16 |
|---:|---:|---:|
| 0.00 s | 36.58% | 23.84% |
| 0.25 s | 38.56% | 26.02% |
| 1.00 s | 44.50% | 32.56% |
| 5.00 s | 76.19% | 67.43% |

This changes the triage decision. If the 25% mask preserves positions, a full-length pass still needs another source of time savings on the first four. A 37.5% mask that preserves both calibration arms deserves a one-recording timed trial, with little headroom for any repair. Even a 50% ceiling on alternating short lanes cannot repay five seconds of extra per-recording wait on either roster under this model. Checking the scientific effect requires actually rebuilding the graph and position from the retained measurements. The calculation reads signed pair metadata for sixteen enrolled assignments and saved timing receipts. It opens no waveform, runs no solver, and measures no new position.
