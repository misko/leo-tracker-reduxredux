# Metadata correlations: negative screen versus untested identity

The historical DS7/DS8 metadata screen contains 24 candidate attributes.
Eighteen were tested and none passed its multiple-comparison correction;
the minimum Benjamini–Hochberg q-value is **0.5247**. Six attributes involving
conditional satellite identity or orbital geometry lacked enough labelled
sessions and were **not tested**. These abstentions must not be reported as
evidence that the signal contains no identity or position information.

## Scope and controls

The screen represents each visit by its distribution of recovered 60-bit
rotation/inversion families and compares Jensen–Shannon signature distances
with metadata differences. It selected 19 eligible visits, then one visit per
session by recovery support, yielding 12 primary representatives. The audit
independently verifies that those 12 have distinct session identifiers.

The original 4,999 permutations relabel whole representatives, not individual
pair entries. That preserves pair dependencies and avoids treating dozens of
pairs as independent samples. It does not condition simultaneously on channel,
sample rate, quality or receiver effects. Session exchangeability remains an
assumption. BH correction applies to these 18 tested attributes only, not every
experiment in the investigation.

| Attribute family | Primary support | Result |
|---|---:|---|
| Channel, edge, sample rate, dataset, RF frequency, recording time | 12 sessions | No corrected association |
| RX0/RX1 acquisition CFO and their difference | 12 | No corrected association |
| RX0/RX1 clock estimates, pilot coherence, acquisition margin | 12 | No corrected association |
| Accepted count, recovery fraction, strict accepted count | 12 | No corrected association |
| Conditional NORAD ID | 3 | Untested: insufficient support |
| Predicted Doppler and range | 2 | Untested: insufficient support |
| Conditional-label elevation, azimuth and frequency offset | 3 | Untested: insufficient support |

No association here decodes message bits. The signature is a waveform vocabulary
now explained substantially by known T-code structure. An association of its
mixture with metadata would still need residual and cross-visit evidence before
being interpreted as a field. Conversely, a negative distribution-level screen
does not exclude a small identity field elsewhere in the signal.

## Support-count sensitivity

The strongest positive raw rank associations include RX1 pilot coherence
(.322), RX1 acquisition margin (.324), accepted count (.234) and recovery
fraction (.238). Under the saved equal-count sensitivity comparison these are
.127, −.037, .061 and .059 respectively. All are exploratory and already fail
the original correction. The change with support balancing weakens a semantic
interpretation of their raw ranks; it does not prove a particular noise cause.

Later DS7–DS10 identity experiments have broader scope and must be assessed
separately. This old screen neither overrides those experiments nor supplies
additional independent confirmation of their outcomes.

## Reproduction and inventory

`metadata_receipt_audit.py` reads the original CSV and input summaries, verifies
the representative-session uniqueness, independently recomputes all 18 BH
values, and preserves every attribute including the six abstentions. It does
not rerun an already negative permutation screen without a new constraint.

```sh
uv run --no-project --with numpy python reports/2026_09_29_firmware_cluster_reaudit/metadata_receipt_audit.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/association_ledger.py
```

Ignored `local/metadata-receipt-audit.json` records input/method hashes, correction
results and per-feature support. The expanded ledger now has **324 entries**;
entries include negative and untested hypotheses, not just discoveries. All
17 component tests pass. The remaining inventory and firmware-to-RF mapping
work is still open, and the investigation remains active.
