# Decimated conditioned CFO bank

On the combined spectral coarse and fused GLRT path, the largest remaining acquisition stage was the conditioned CFO bank. On segment 3 visit 1536, its warm CPU was 180–207 ms on DS26-0036 and 207–213 ms on DS29-0082, versus 150–173 ms for the fine CFO FFT and 60–72 ms for verification. The profile exercised 24 candidate refinements including the producer's third acquisition pass on the second receiver. The earlier coarse and GLRT changes were locked and shared across both arms of this comparison. [Protocol](PROTOCOL.md)

The candidate mixes the original whole-frame template at the center of the requested CFO interval. It streams IQ through 256-sample blocks and accumulates frame energy and six centered polynomial moments per block. The direct 41-by-13,333 complex phase bank reduces to 41-by-318. The center-to-center phase remains an exact exponential at each requested CFO. Inside each block, degree-five Taylor evaluation represents the remaining phase. The complex exponential remainder on the real phase axis is bounded by the sixth power of the maximum block phase divided by `6!`. Cauchy–Schwarz bounds the error after the original frame-energy normalization. The score enclosure also budgets finite FP64 phase, dot product and energy errors. At a 4 kHz total search span the truncation bound is about `2.35e-8` normalized score.

The fast path requires a separated winning interval, recomputes the winner's score with a direct FP64 dot product, and otherwise calls the original conditioner. The full output retains the same acquired CFO, GLRT64 timing and scores. The original winner's intermediate conditioned score can differ by ordinary FP64 summation roundoff. If the acquisition scheduler could use that score to order different emitted GLRT hypotheses, the wrapper reruns acquisition with the original conditioned bank. Equal verified-score groups with identical epoch and binary acquired CFO can pass without a retry, because the GLRT scorer reads those two values at each rank. The regression includes signed-zero CFOs, which are physically equivalent and still trigger the original fallback because their serialized values differ.

## Initial guard

The initial implementation retried acquisition on every sort-key tie. All 24 scheduled payloads matched the installed producer, including two exclusions. The held-conditioned stage saved 40.3% CPU, while full detector CPU rose from 42.333 to 45.371 seconds across the valid holdout and extension repeats. DS26 spent an extra 192 conditioned bank calls on whole-acquisition rank-tie retries. This run missed the timing gate and produced detector-only evidence. The subsequent revision changed the observable-equivalence check and left the moment kernel, enclosure, and timing thresholds fixed before a new blind roster. [Initial qualification](whole-retry/qualification.json) · [Initial detector-only result](whole-retry/positions.jsonl.gz)

## Revised guard

The revised conditioner passed the prespecified timing gate on the established holdout and extension. Total full detector CPU fell from 39.047 to 33.329 seconds, a 14.7% saving. Conditioned bank CPU fell from 8.366 to 3.197 seconds, a 61.8% saving. The separate blind sample showed smaller full savings on DS26 and retained the distinction between duplicate and observably different hypotheses. One blind DS26 visit legitimately retried acquisition. The two processes ran concurrently on CPU 14 and 15 with one numerical thread each. [Qualification summary](qualification.json)

| Recording and split | Valid / scheduled | Median CPU, control → revised | Full CPU saved | Conditioned CPU saved |
| --- | ---: | ---: | ---: | ---: |
| [DS26-0036 development](DS26-0036-development.json.gz) | 4 / 4 | 0.726 → 0.627 s | 14.0% | 61.8% |
| [DS26-0036 holdout](DS26-0036-holdout.json.gz) | 4 / 4 | 0.743 → 0.638 s | 13.5% | 60.5% |
| [DS26-0036 extension](DS26-0036-extension.json.gz) | 4 / 4 | 0.935 → 0.784 s | 15.8% | 63.5% |
| [DS26-0036 blind](DS26-0036-blind.json.gz) | 4 / 4 | 0.719 → 0.641 s | 2.9% | 48.9% |
| [DS29-0082 development](DS29-0082-development.json.gz) | 3 / 4 | 0.816 → 0.652 s | 13.0% | 62.6% |
| [DS29-0082 holdout](DS29-0082-holdout.json.gz) | 3 / 4 | 0.781 → 0.670 s | 9.8% | 59.7% |
| [DS29-0082 extension](DS29-0082-extension.json.gz) | 4 / 4 | 0.802 → 0.661 s | 18.2% | 62.7% |
| [DS29-0082 blind](DS29-0082-blind.json.gz) | 2 / 4 | 0.770 → 0.707 s | 13.9% | 64.1% |

Conditioning arrays peaked at 0.92 MB. Peak traced full-visit allocations rose from 24.72 to 24.79 MB on DS26 and from 24.74 to 24.79 MB on DS29. Median CPU still exceeded 30 times the 20 ms RF duration on either recording. Timings exclude archive reads, compiler work, and the additional untimed dense audit.

All 32 scheduled archive payloads matched exactly, including four exclusions. Candidate ranks, integer epochs, fractional corrections, acquired and tracking CFO, scores, and gate winners matched the installed producer. Across 151 audited moment-bank maps, the worst approximation error was `7.60e-11`, the worst direct winner error was `5.55e-17`, and every certified winner matched. The strong plant recovered epoch 731 and CFO within 0.1 Hz on all four receiver lanes. The faint plant also recovered epoch 731 on all four lanes, with at most 7.3 Hz winner CFO error. The mixed adjacent-CFO control matched every candidate and its best fractional result used epoch 928 on all lanes. Empty IQ produced no positives. An independent unmodified-producer call for each synthetic control matched both the input and full output digests. [DS26 synthetic digest audit](DS26-0036-synthetic-original.json) · [DS29 synthetic digest audit](DS29-0082-synthetic-original.json)

## Fresh partial-IQ positions

The full no-repair v5 engine freshly fit one revised-guard composite per recording. Sixteen scheduled visits per recording came from the detector trial. DS26 provided 16 valid fresh IQ visits and 6,749 archived valid visits. DS29 provided 12 fresh valid IQ visits and 4,856 archived valid visits and reproduced its four sampled capture exclusions. The comparator used the earlier freshly fitted capture-era controls on their exact original archive bytes. The trial and control worker requests matched on all scientific settings after excluding the separately bound input and output identities. Prepared observations, tracks, final satellite ownership, position coordinates, conditional RMS, and frequency scores matched exactly within each calibration arm. [Revised positions](positions.jsonl.gz) · [Capture-era controls](control-positions.jsonl.gz)

| Recording | Error `c0` / `fitted_c` | Conditional Doppler RMS `c0` / `fitted_c` | Fresh v5 CPU / wall |
| --- | ---: | ---: | ---: |
| DS26-0036 | 1.278365 / 1.208143 km | 74.760916 / 74.682298 Hz | 208.14 / 210.57 s |
| DS29-0082 | 0.566947 / 0.517230 km | 97.003569 / 96.683622 Hz | 133.17 / 134.67 s |

The two position-error medians were 0.922656 km for `c0` and 0.862686 km for `fitted_c`, with interpolated 95th percentiles of 1.242794 and 1.173597 km. The bundle gives coordinates, RF fit scores, and input and arc digests for both arms of the paired partial replay. [Position-error distributions](error-distributions.json)

## Reproduction

Pin CPU 14 for DS26 or CPU 15 for DS29 and set all five numerical thread environment variables in `THREAD_ENV` to one. Put the capture-era producer first on `PYTHONPATH`. Run `tools.pipeline_eval.qualification.conditioned_cfo_eval` with `--case`, `--split` and `--out`. The blind split requires a local 32 MiB read cap to preserve the fixed IQ roster and the existing verified reader. For example, run the following under the same pinned environment.

```sh
.venv/bin/python -B - --case DS26-0036 --split blind --out /tmp/ds26-conditioning-blind.json.gz <<'PY'
from unittest.mock import patch
from tools.pipeline_eval.qualification.conditioned_cfo_eval import main
from tools.pipeline_eval.variants import iq_stream

with patch.object(iq_stream, "MAX_CHUNK_PREFIX", 32 * iq_stream.MIB):
    main()
PY
```

Use `tools.pipeline_eval.qualification.conditioned_cfo_position --gate --report <directory>` to validate the detector evidence. Use `--case` and `--work` with the report path to fit a paired partial-IQ composite, then `--package` for both roster rows.

The expanded position work for this run is under `/srv/bulk/leo-dev/conditioned-cfo-position-20261119-P5wY65`. The compact bundles are the primary report artifacts.
