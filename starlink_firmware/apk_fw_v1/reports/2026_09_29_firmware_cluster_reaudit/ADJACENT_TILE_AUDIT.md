# Adjacent regions do not preserve the observed partitions

The saved adjacent-tile experiments contain six comparisons: upper/lower edge
and widths of 8, 16 or 32 OFDM symbols. Each edge uses 24 selected 10 MS/s
tracks from DS7–DS9, deduplicated by session/visit/channel. Shift and phase were
fit on one reserved frame and frozen on the second. This audit reproduces the
saved hierarchy and metrics; it does not search new alignments or recordings.

| Edge | Symbols | Adjacent four-group ARI | Pair-matrix Spearman | Mean held shift gain |
|---|---:|---:|---:|---:|
| Upper | 8 | .0236 | −.0009 | −.00485 |
| Upper | 16 | .0237 | .1127 | .00540 |
| Upper | 32 | −.0509 | .0151 | .00431 |
| Lower | 8 | −.0137 | −.0288 | −.00556 |
| Lower | 16 | .0247 | −.0340 | −.00378 |
| Lower | 32 | −.0348 | .0330 | .00460 |

ARI compares group assignments, with 1 meaning identical partitions and values
near zero meaning little agreement beyond its combinatorial baseline. These
results do not support a stable four-group signature recurring in adjacent
regions. They do not prove absence of message bits: changing messages, coding,
noise or imperfect alignment can also prevent transfer.

## Geometry and control audit

Each saved average-linkage tree reproduces from its stored pair similarities
to absolute tolerance 1e-12. We also tested whether the pair-specific fitted
transformations made the similarities inconsistent with a common Euclidean
embedding. All 12 held/adjacent unit-diagonal Gram matrices are positive
definite; their minimum eigenvalues range from .00988 to .57838. Thus this
particular potential geometry failure does not explain the weak recurrence.
This is a numerical check, not validation of satellite identity or of a
physical interpretation of the embedding.

A node permutation preserving session, channel, sample rate and receiver can
move only **two of 24 tracks** in each edge cohort. There is one group of size
two and 22 singletons, yielding only **two distinct permutations**, including
the observed ordering. Repeatedly drawing 999 shuffles would not create 999
independent reference configurations. The audit therefore abstains from a new
permutation significance claim. It does not relax the strata or shuffle pair
entries as if they were independent observations.

## Receiver agreement is a different association

The historical paired-tile receipts for S23 and DS9-middle contain six
width-specific receiver comparisons and ten known-state regional comparisons.
They are now included individually in the ledger, with original metrics and
source hashes. Their matched-receiver agreement supports recovery of a shared
waveform. It does not imply that different visits or adjacent regions preserve
the same cluster membership.

The regional state comparisons group frames by known recovered T-state,
**not by satellite identity**. In particular, the stronger same-state effect
in later regions cannot be counted as a newly discovered identity field.
Those historical receipts and their original shifted/permuted controls are
preserved; no new inferential claim is made from rereading them.

## Firmware interpretation and reproducibility

The fresh firmware constraints do not supply a physical translation between
these tile regions. Device-role settings are configuration, the 20-entry
routine is a threshold mask, and the neighboring 60-entry mask is not directly
the recovered T-code. None establishes repeated header-field boundaries here.
The highest-ranked explanations remain region-dependent waveform content,
known-state mixture and uncertain alignment/noise. A stable encoded-field or
satellite-signature interpretation lacks the required transfer evidence.

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_firmware_cluster_reaudit/tile_receipt_audit.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/association_ledger.py
```

Outputs remain ignored under `local/`. The ledger adds 22 associations and now
contains 300 entries, including historical public-reference groups explicitly
separated from local observations. This count is not a count of discoveries.
The broader 195-artifact semantic inventory remains unfinished. No IQ,
firmware input, golden fixture or unrelated work was changed.
