# Unpruned spectral rewrite inside the original detector

On 20 saved stereo visits, both unpruned rewrites preserved all 384 ranked candidate responses through 48 physical attempts, including eight retries. The batched workspace cut the median profiled spectral time from 5.10 to 3.98 ms per visit. That seam used 0.84% of original total detector CPU in the profile. The complete detector took **4.95 ms more CPU at the paired median** with the batched workspace. The split scorer took **4.00 ms more**. [Stage chart](stage.pdf) · [Paired timing](summary.csv) · [Candidate parity](attempts.csv)

## Scorer and comparison

The original detector passes the exact and rolled-control fractional symbol correlations to one paired scorer. On the supported 64-symbol geometry, the original does one short forward FFT call for both references, then one inverse and one final forward FFT call per reference. The split version computes both reference peaks separately behind one geometry check. The batched version validates the same geometry once, reuses a bounded workspace and dispatches both branches together at each of the three transform stages. The number of underlying transforms across rows stays the same. The saved work is dispatch and setup, intermediate allocation and repeated validation. Both new paths compute the exact and control spectra for every candidate. Unsupported geometry uses the installed original path. [Bounded scorer](../../../../tools/pipeline_eval/variants/spectral_rewrite.py) · [Protocol](PROTOCOL.md)

| Scorer | Short forward dispatches | Inverse dispatches | Final forward dispatches |
|---|---:|---:|---:|
| Original paired | 1 | 2 | 2 |
| Unpruned split | 2 | 2 | 2 |
| Batched workspace | 1 | 1 | 1 |

The frozen panel covers 20 genuine stereo visits, lower and upper edges, four recordings and three producer roots. Each recording contributes dual-positive, single-lane, negative and near-gate cases selected in the earlier raw qualification, plus one passing tie selected from archived factors. These are detector stress cases. Runtime estimates apply to the measured sample. Every full call starts with saved CI16 resident and runs the same prepared row-wise acquisition, exact fine-search kernel, integer batch, fractional interpolation and public projection. [Input lock](input-lock.json)

The detector outputs were compared field for field with the paired pipeline. Native probe output was also compared with the original capture archive. This checks both passing and rejected responses in the public output, and both compact input factors on every visit. In addition, the per-attempt audit includes unsuccessful primaries replaced by fallback. The evidence stops at the original native position inputs. [Attempt and payload ledger](attempts.csv) · [Qualification seal](qualification-lock.json)

## Complete detector CPU and wall time

The complete saved-window detector ran five interleaved repeats per visit and variant on CPU 13. Median paired differences use original minus candidate within the same visit and repeat. The profiled calls were separate and counted the spectral function from entry through geometry checks, setup and both scores. All modes invoked that function 243 times across the profiled visits. [All repeated timings](timing.csv) · [Spectral profile](profile.csv)

| Scorer | Median full CPU (ms) | Median paired CPU saved (ms) | Total CPU saved (%) | Median paired wall saved (ms) | Median profiled spectrum CPU (ms) | Profile CPU in spectrum (%) |
|---|---:|---:|---:|---:|---:|---:|
| Original paired | 458.13 | 0.00 | 0.000 | 0.00 | 5.10 | 0.837 |
| Unpruned split | 463.77 | −4.00 | −0.654 | −7.41 | 3.83 | 0.667 |
| Batched workspace | 462.76 | −4.95 | −0.099 | −7.69 | 3.98 | 0.697 |

The batched full detector had a positive paired CPU median on DS29-0519, where it saved 1.82 ms. The other three recordings had negative medians. The pooled full-detector result provides no measured speed gain on this host and sample. The earlier 24% spectral-stage result measured resident correlations only. [Per-recording distributions](summary.csv) · [Earlier resident-spectrum experiment](../../coarse-and-navigation/winner-bound/)

## Memory

Separate processes replayed the same four passing-tie visits, one per recording and mode. Median process peak RSS was 174.50 MiB for original paired, 173.78 MiB for split and 174.48 MiB for batched. These peaks include runtime and source staging. The batched numerical workspace has 161,792 bytes of resident array capacity. Both candidate versions also use a frequency-grid cache bounded to 128 grids of 512 doubles, or 512 KiB of array payload at capacity. [Independent RSS measurements](memory.csv)
