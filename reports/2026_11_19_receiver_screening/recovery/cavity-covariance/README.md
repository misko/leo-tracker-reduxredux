# Low-rank cavity covariance in compact v5

The candidate replaces the dense covariance used to rank coarse replacement proposals. Both workers start from the same capture-era native detector factors and causal catalogue and finish through the complete compact v5 receiver. The original fine proposal evaluation, candidate gates, restored replacements, and subsequent recovery stay in the paired computation.

The covariance combines diagonal point noise, one independent 300 Hz constant per held source, and the small radio calibration covariance. The low-rank score first whitens the diagonal and independent source constants with rank-one projections. It then integrates the radio modes in their own space and forms the augmented residual from the posterior residual and prior norm. A determinant lemma supplies both covariance log determinants. Phase is integrated against the same prior. Batches of 48 candidates limit transient residual and phase arrays. Whole-source CFO aliases use the original native-Hz reduction order. When an adjacent rank is numerically ambiguous, the source-verified dense scorer supplies its original ordering.

The source-verified overlay reads the pinned `family_cavity.py` and `cavity_prediction.py` bytes. The specific `family_data` covariance field feeds only the coarse nomination scorer. The two-family joint evidence makes its own covariance independently, so its work remains part of the original receiver. The report records memory at process and stage boundaries, including the high-water mark inherited from earlier stages.

## Original schedule

DS26-0036 reproduced all 24 family rankings and aliases, 192 fine candidates, 696 per-source residual vectors, the restored replacement decisions and both final positions exactly. The residual comparison checks every source vector by SHA-256 and records its RMS. The dense fallback was unnecessary for these 24 families.

| DS26-0036 measurement | Fresh compact v5 | Low-rank nomination |
| --- | ---: | ---: |
| Full worker CPU | 102.099 s | 103.040 s |
| Full worker wall | 129.614 s | 131.325 s |
| Full worker peak RSS | 1,432,608 KiB | 1,428,512 KiB |
| Coarse scorer CPU | 0.110 s | 0.169 s |
| Complete nomination CPU | 6.945 s | 7.067 s |
| Coarse-stage process high-water | 1,394,096 KiB | 1,363,148 KiB |
| Largest dense covariance or radio mode array | 476,288 bytes | 58,560 bytes |

The smallest array footprint is specific to these covariance representations. It excludes the rest of the phase geometry and row workspace. The measured case spent more CPU in the new scorer. Process high-water includes the rest of the computation.

DS29-0082's dense control completed and the candidate reached its original 260-second worker cap. The salt-selected DS26-0024 replay completed its candidate leg and reached the remaining common deadline in its stock leg. The launch window for the second salt-selected case, DS29-0127, had closed. The primary and salt-selected charts retain the original statuses.

## Same-input repeats

The DS29-0082 candidate and the DS26-0024 stock leg each completed in a separate repeat on the original pinned core. Both matched the completed leg of the original schedule. Across all three complete pairs, every coarse rank and alias matched for 60 families, every fine candidate matched for 480 candidates, and all 1,672 per-source residual vectors matched. Restored trials, selections, final owned counts, frequency metrics and both calibration endpoints were exact. All measured coarse scores used mode space.

| Fresh comparison | Full CPU, stock → candidate | Full peak RSS, stock → candidate | Coarse CPU, stock → candidate | Largest dense covariance → radio mode array |
| --- | ---: | ---: | ---: | ---: |
| DS29-0082 | 120.765 → 128.719 s | 1,294,524 → 1,308,472 KiB | 0.074 → 0.127 s | 520,200 → 61,200 bytes |
| DS26-0024 | 127.742 → 126.514 s | 1,527,052 → 1,495,944 KiB | 0.137 → 0.160 s | 1,384,448 → 99,840 bytes |

The repeats ran in separate sessions under different CPU contention. The largest covariance representation shrank by 92.8%. The new coarse scorer used more CPU in each observed comparison, and the full worker peak varied. The repeat chart shows the completed comparisons alongside the original schedule's distinct pages.

[Prospective timing and selection protocol](PROTOCOL.md) · [Nomination and restoration audits](stage-receipts.jsonl.gz) · [Both-arm position and frequency scores](scores.csv) · [Paired summaries](summary.json)
