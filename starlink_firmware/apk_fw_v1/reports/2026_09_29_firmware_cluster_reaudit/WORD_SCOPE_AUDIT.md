# Known-state stability and unmatched words, separated by quality

A fresh recount of all **350 existing DS7–DS10 decode receipts** confirms
within-frame T-state consistency, while separating pilot-qualified tracks from
all accepted-window results. Every source receipt matches its recorded SHA256.
No raw IQ was newly decoded and no word search was expanded.

| Dataset | Qualified track/frame cases with multiple known-state windows | Cases agreeing on one state | Qualified two-frame tracks | State changes |
|---|---:|---:|---:|---:|
| DS7 | 105 | 105 | 57 | 55 |
| DS8 | 77 | 77 | 36 | 35 |
| DS9 | 255 | 255 | 129 | 123 |
| DS10 | 434 | 434 | 206 | 186 |
| Total | **871** | **871** | **428** | **399** |

The old all-accepted count of 1,091 multiwindow track/frame cases includes
220 cases from tracks that failed pilot qualification. Removing them leaves
the within-frame consistency result intact. All 428 eligible two-frame tracks
were already qualified, so that count does not change.

These are track/frame/window units, not independent satellite observations.
They use the original qualification list, before the later one-entry physical
deduplication, and multiple receivers/tracks can observe related signals.
The table describes accepted exact generator matches; it makes no statement
about windows that fail acceptance or contain unknown words.

## What the unmatched words show

The audit independently recomputes minimum Hamming distance to every word
in the existing 60-state codebook for all 35 unmatched accepted windows:

| Track quality | Distance 1 | Distance 2 | Distance 30 |
|---|---:|---:|---:|
| Qualified | 20 | 2 | 0 |
| Insufficient pilots | 8 | 0 | 5 |

Thus all **22 qualified unmatched windows** are one or two bits from known
T-code words. The five large deviations all come from unqualified DS9 tracks.
That substantially weakens interpreting the large deviations as a new word
family. It does not prove every small deviation is an error: independent
receiver/held-window reproduction is still needed to distinguish distortion
from additional structure. Acceptance here is a decoder criterion, not a
validated payload checksum.

## Meaning for clustering and firmware

The state is consistent across multiple accepted windows of a frame but
usually changes between the two sampled frames (399/428, approximately 93%).
That supports a frame-dependent known-waveform state, rather than a constant
raw satellite identifier. It does not establish a counter, timestamp or
satellite-specific sequence rule. The prior counter and identity tests remain
the relevant evidence for those stronger interpretations.

Word-family clusters therefore need known-state mixture separated from possible
message content. The fresh firmware's 60-entry threshold table cannot directly
generate these nonconstant words under the tested transformations. No firmware
field has been mapped to the unmatched bit coordinates. The word vocabulary
and its occasional near-neighbors must not be described as decoded SATAddr.

## Reproduction

```sh
python3 reports/2026_09_29_firmware_cluster_reaudit/word_scope_audit.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/association_ledger.py
```

Ignored `local/word-scope-audit.json` preserves dataset/quality counts, checked
distances, source hashes and limitations. The ledger adds four stability
associations and seven quality/dataset novelty categories, reaching **371
entries**. All 21 research-component tests pass. The research objective remains
active; the report does not claim a completed semantic decode.
