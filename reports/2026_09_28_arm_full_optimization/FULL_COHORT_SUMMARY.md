# Full host cohort independent summary

The completed host screen contains 704 metadata-selected dwells from all 88
recordings represented in the sealed DS7-large ARM corpus. It is a quality
comparison over that saved corpus. It is not the full DS7 dataset, and its
timings are not ARM timings.

The independent audit reconstructed every denominator from the selected
manifest and the sealed `original`, repeat-0 baseline. It required 704 unique
cases, exactly 22 receiver/probe windows per case, and exactly eight candidates
per window. The resulting inventory is 15,488 windows and 123,904 candidates;
no native case or window is missing.

| Rate | Dwells | Windows | Candidates | Positive windows, reference/native | Positive hits, reference/native/recovered | Ordered mismatched windows/candidates |
|---:|---:|---:|---:|---:|---:|---:|
| 2.5 MHz | 152 | 3,344 | 26,752 | 1,682 / 1,682 | 4,573 / 4,573 / 4,573 | 0 / 0 |
| 5 MHz | 216 | 4,752 | 38,016 | 1,874 / 1,874 | 5,466 / 5,466 / 5,466 | 0 / 0 |
| 7.5 MHz | 184 | 4,048 | 32,384 | 1,933 / 1,933 | 5,186 / 5,186 / 5,186 | 1 / 4 |
| 10 MHz | 152 | 3,344 | 26,752 | 1,518 / 1,518 | 4,356 / 4,356 / 4,356 | 0 / 0 |
| **Total** | **704** | **15,488** | **123,904** | **7,007 / 7,007** | **19,581 / 19,581 / 19,581** | **1 / 4** |

Positive-hit recovery uses maximum-cardinality one-to-one matching within each
window, with at most two samples of epoch difference and 8 kHz of tracking-CFO
difference. A native candidate therefore cannot receive credit for more than
one baseline candidate. All 19,581 baseline-positive candidate hits were
recovered, with no added positive hits; all 7,007 baseline-positive windows
remain native-positive.

Ordered scientific parity separately compares rank-aligned epoch, acquired and
tracking CFO, exact score, control score, and margin. The tolerances are exact
epoch, 2e-6 Hz CFO, and 2e-9 score. Exactly one window differs: ordinal 306,
receiver 0, probe 3, where ranks 1 through 4 differ. All affected candidates
remain below the 0.025 positive gate, so positive-hit recovery is unchanged.
This audit establishes the location and extent of the change; it does not
attribute a cause.

The machine-readable result is in
[`FULL_COHORT_SUMMARY.json`](FULL_COHORT_SUMMARY.json). The archived evidence in
[`results/screen704`](results/screen704) contains the build receipt, completed
selection manifest, and deterministically gzipped raw JSONL. The recorded
uncompressed raw SHA-256 is
`386d03888b198dd8474ae5cf851a9600c9779592e683a10d0f0d4bc7e383e237`.
