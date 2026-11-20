# Position error for every receiver modification

The gallery has **one page per modification**. The original ten use the same 127 DS26 and eight DS29 recordings. Each subsequent page names its own sample size. Every page shows all four v5 configurations on exactly those recordings. The upper curve counts all recordings, including withheld fixes. Each dot is a returned position and the diamond is their median. The dashed forced curve includes estimates that the receiver chose to withhold. [Illustrated gallery](figures/fitted_c/README.md) · [19-page PDF](figures/fitted_c/modifications.pdf) · [Zero-calibration PDF](figures/c0/modifications.pdf) · [All recording-level errors](figures/fitted_c/modifications.csv)

## Accelerated capture-era GLRT

Computing the coarse pilot score grid took 12.52 of 18.87 profiled seconds on DS26 and 11.04 of 16.50 seconds on DS29. The detector also built a Python heap over local peaks and repeatedly calculated the same interpolation weights. The candidate computes the full score grid with a 42-line C short-filter kernel, selects the local peaks with array operations, and reuses the interpolation weights at a common fractional offset. It keeps the original fine search, fractional scores, thresholds and receiver fallback. A complex-double matrix formulation provided a numerical reference. [Filter kernel](../../tools/pipeline_eval/variants/anchor_filter.c) · [Score and sampling implementation](../../tools/pipeline_eval/variants/anchor_grid.py)

The test used four fixed windows in each of four later segments per recording. Each decoded IQ window went through both complete capture-era detectors, alternating their run order. Wall time below is the median per valid 20 ms window, timed after IQ decoding on one pinned Intel Core Ultra 9 285K CPU with single-threaded libraries. The five invalid DS29 windows were excluded identically. [Frozen experiment plan](PROTOCOL.md) · [DS26 detector measurements](DS26-0036-detector.json.gz) · [DS29 detector measurements](DS29-0082-detector.json.gz)

| Recording | Valid / scheduled | Complete receiver candidate lists | Exact candidate records | Original → accelerated detector | Ratio of medians |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 16/16 | 32/32 | 256/256 | 2.376 → 1.115 s | 2.13× |
| DS29-0082 | 11/16 | 22/22 | 176/176 | 2.364 → 1.146 s | 2.06× |

The exact comparison includes every candidate field and all downstream probe rows. Single precision in the coarse grid can change the ordering of very close peaks on other inputs. These runs used GCC 15.2 and host vector instructions. A target-board real-time result requires measurement there.

For the position experiment, each recording used the new detector for the 16 scheduled windows and its original archived detections for the remaining visits. Both v5 position fits then ran from those observations. Errors were 1.278 km and 0.567 km with zero calibration, and 1.208 km and 0.517 km with fitted calibration, in DS26 and DS29 order. Both coordinates matched the original endpoints in both arms. The host detector timing applies only to the measured windows. [Position chart](figures/fitted_c/anchor_receiver.png) · [Fresh position predictions and timing boundaries](partial-iq-position.jsonl.gz)

## Shared-clock Doppler position fit

This receiver starts at anonymous tracks. It estimates horizontal position, clock offset and drift per receiver and band, one timing correction per satellite, and optional RF calibration. It checks each region against held-out tracks before allowing publication. Satellite assignments, integer frequency ambiguities, weights, priors, region and search budget are fixed across the two calibration arms. All thresholds were fixed before examining the larger panels. [Receiver](../../tools/pipeline_eval/variants/shared_doppler.py) · [Single-tile predictions](single-tile.jsonl.gz) · [DS26 four-region predictions](ds26-four-offers.jsonl.gz) · [Four-region DS29 and small-panel predictions](roof16-four-offers.jsonl.gz)

| Receiver and calibration | DS26 fixes | Median / P95 km | Within 5 km, all 127 | DS29 fixes | Median / P95 km | Within 5 km, all eight |
|---|---:|---:|---:|---:|---:|---:|
| Original v5, fitted | 127 | 0.999 / 3.126 | 125 | 8 | 0.742 / 1.312 | 8 |
| Shared-clock, fitted | 92 | 2.004 / 5.207 | 84 | 6 | 2.034 / 5.063 | 5 |
| Original v5, zero | 127 | 0.988 / 3.084 | 125 | 8 | 0.753 / 1.210 | 8 |
| Shared-clock, zero | 92 | 2.046 / 5.251 | 82 | 6 | 2.070 / 5.000 | 5 |

Here v5 uses the original roof tile and the candidate receives the four regions from the earlier comparison. The chart also shows the candidate on the same single tile as v5. With fitted calibration, that restored coverage to 94/127 on DS26 and yielded 5/8 on DS29. The four-region track-to-position search took a median 0.44 s on DS26 and 0.58 s on DS29 on this host. IQ decoding, GLRT and track formation precede that timer. [Four-region, single-tile and forced errors](figures/fitted_c/shared_doppler.png) · [Zero-calibration errors](figures/c0/shared_doppler.png)

On the common adopted tracks across all roof attempts, the median per-recording unweighted Doppler RMS fell from 219.0 to 206.8 Hz on DS26 and from 194.3 to 167.1 Hz on DS29 with fitted calibration. The DS29 position P95 increased slightly. The solver falls outside the requested accuracy and coverage range for replacing v5. [Both arms' fitted parameters and residuals](ds26-four-offers.jsonl.gz)

## Geographic transfer and missing regions

The 124 queries pair the same 62 acquisitions with the correct region present and missing. The eight DS29 roof recordings also appear in the roof chart. The 11 StarLoc recordings represent eight nearby site groups at a separate installation. The Altrincham inputs have no tracks. This is a frozen retrospective transfer panel. The method received anonymous regions, causal orbital information and observations. Scoring used surveyed truth afterwards. [Transfer error for every query and arm](transfer-errors.csv) · [Predictions and withholding reasons](transfer.jsonl.gz)

| Acquisition family | Correct region present, published | Correct region missing, published |
|---|---:|---:|
| DS29 roof recordings | 6/8 | 0/8 |
| StarLoc recordings | 0/11 | 0/11 |
| Altrincham empty windows | 0/3 | 0/3 |
| Simulated locations | 0/40 | 0/40 |

On StarLoc, two recordings had too few usable tracks and nine failed the held-track support check. All 40 simulated locations also failed that check with the correct region present. The missing-region result alone therefore gives a misleading impression of geographic performance. [Scored distributions](transfer-summary.json)

## Reproduce the figures

Run the first command from the repository root to regenerate the complete gallery from the published numerical evidence. The second selects a single modification. Both default to matched fitted and zero-calibration comparisons.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel published --out /tmp/receiver-figures
.venv/bin/python -m tools.pipeline_eval figures --panel published --variant shared_doppler --out /tmp/doppler-figures
```

On the corpus host, these commands repeat the receiver measurements. The first also compiles the detector with the host C compiler and invokes each recording's verified capture-era producer. The four-region commands check the original observation, orbit catalogue and region-offer identities. The final command packages the new predictions and both arms' transfer errors.

```sh
OUT=/tmp/receiver-eval
DATA=/tmp/receiver-evidence
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
.venv/bin/python -m tools.pipeline_eval run --panel smoke --variant anchor_receiver --jobs 2 --pin --require-inputs --out "$OUT"
for panel in roof16 ds26-common127 transfer124; do
    .venv/bin/python -m tools.pipeline_eval run --panel "$panel" --variant shared_doppler --jobs 4 --pin --require-inputs --out "$OUT"
done
.venv/bin/python -m tools.pipeline_eval.qualification.roof_replays --method shared_doppler --panel ds26-common127 --jobs 4 --out "$DATA/ds26-four-offers.jsonl.gz"
.venv/bin/python -m tools.pipeline_eval.qualification.roof_replays --method shared_doppler --panel roof16 --jobs 2 --out "$DATA/roof16-four-offers.jsonl.gz"
.venv/bin/python -m tools.pipeline_eval.qualification.shared_evidence --runs "$OUT" --out "$DATA"
.venv/bin/python -m tools.pipeline_eval figures --panel published --variant shared_doppler --variant anchor_receiver --evidence "$DATA" --out /tmp/fresh-receiver-figures
```
