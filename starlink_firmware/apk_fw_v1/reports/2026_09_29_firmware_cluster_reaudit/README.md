# Fresh firmware and hierarchical-association audit

Status: active investigation, September 30, 2026. This is an ongoing audit,
not a completed review of every association.
The [plan](PLAN.md) records remaining work. Existing DS7/DS8/DS9/DS10 and firmware
only; no new RF. Earlier sealed results, fixtures and unrelated changes are preserved.

## Executed follow-up reports

- [Firmware-to-signal synthesis and illustrated conditional message layouts](FIRMWARE_SIGNAL_BRIDGE.md).
- [Portable illustrated review and searchable association ledger](local/review.html),
  built by `publish_review.py` with source-hash verification.
- [Primary-literature constraints and reasons not to repeat previous scans](LITERATURE_CONSTRAINTS.md).
- [Prefix branches and actual bit-writer execution](PREFIX_BRANCHES.md).
- [Early-profile tree stability](EARLY_TREE_STABILITY.md) and
  [changes when DS10 is added](CORPUS_EXTENSION.md).
- [Held-frame transfer](FRAME_TRANSFER.md),
  [which observations contribute](TRANSFER_ATTRIBUTION.md), and
  [phase and quality sensitivity](PHASE_SENSITIVITY.md).
- [All seven frozen symbol pairs, expanded association ledger and actual
  variant-loader execution](PAIR_AND_VARIANT_AUDIT.md).
- [Connected initialization and decoded device-role names](INITIALIZATION_ROLES.md).
- [Role setter and reciprocal transmit/receive parameters](ROLE_CONFIGURATION.md).
- [Threshold-mask builder and hardware-register consumer](CONFIGURATION_MASK.md).
- [60-entry table versus the recovered T-code](SIXTY_ENTRY_AUDIT.md).
- [Adjacent tile partitions, geometry and control support](ADJACENT_TILE_AUDIT.md).
- [Metadata screen, correction and untested identity attributes](METADATA_AUDIT.md).
- [Phase-histogram trees and loss of symbol ordering](PHASE_HISTOGRAM_AUDIT.md).
- [Joint receiver controls for early I/Q structure](RECEIVER_FAMILY.md).
- [Qualified T-state stability and unmatched-word scope](WORD_SCOPE_AUDIT.md).
- [Identity controls, revisit support and stable-pattern specificity](IDENTITY_SCOPE_AUDIT.md).
- [Wider-carrier identity and known-waveform reliability](BANDWIDTH_SCOPE_AUDIT.md).
- [Counter-model ambiguity and conservative numerical ties](COUNTER_TIES.md).
- [Frozen amplitude models and neighboring-symbol associations](AMPLITUDE_AUDIT.md).
- [Actual receive-parser feature and prefix branch gate](PARSER_GATE.md).

The pair batch finds no individually supported pair after the 21-test cyclic
family correction, and verifies different destination-pointer object offsets
in the two PHY variants. The ledger now includes 685 association/hypothesis entries;
these are not 685 discoveries. No recovered feature is established as satellite
identity or a mapped message field.

The connected initialization audit establishes that mode 3 is `SAT-RX`,
mode 4 is `UT-TRX`, and default 5 is `UNSET`. These device-role settings cannot
be assigned to per-frame cluster splits. Eight executed cases verify another
98,304 table writes and the distinct register predicates. Later batches above
extend the original checks; use the full component test command below.

## Direct firmware inspection

`raw_audit.py` reads five existing AArch64 ELF binaries, independently verifies
their architecture/endianness, translates virtual addresses through file-backed
load segments, and disassembles the selected routines. It does not use prior
disassembly text as evidence. Binary/window SHA256 and complete instructions are
saved in ignored `local/raw-audit.json`. All selected code windows happen to have
equal virtual and file offsets; this is verified, not assumed. The address mapper
rejects ambiguous mappings and memory-only BSS bytes.

| Evidence from raw instructions | Assessment |
|---|---|
| `tx_lmac` 0x7dd5c–0x7dd70 loads a byte, sets `1 << w21`, ORs it with the byte, masks to eight bits and stores it | Supports a bitmap update; weakens any interpretation of this operation as incrementing a frame counter |
| At 0x7dd74–0x7dd80, equality selects `w22=2`; the mismatch/logging path also sets 2 at 0x7ddc4 | Value 2 is not a unique indication of map equality; do not label a two-cluster split “match/mismatch” from this evidence |
| Prefix builder 0xc1378 masks the caller value to two bits; 0xc13a4 inserts it at software prefix bits 4–5 | Confirms software packing width. It establishes neither air-interface bit order nor an RF coordinate |
| Prefix construction has branches and a subsequent variable-width writer call at 0xc13e0 | Later prefix and caller executions constrain software packing; an RF bit-position mapping remains unverified |
| `rx_lmac` 0x27164 calls metadata-copy helper; 0x27224 loads the copied length and 0x27228 loads a separate pointer at descriptor+0x10 | Preserves the descriptor/payload distinction; descriptor offsets must not be assigned directly to RF symbol positions |
| Canonical PHY setup constants and variant CGM loader instructions are re-disassembled from ELF-mapped bytes | Hardware configuration exists, but opcode/field meaning and RF coding remain unresolved; further initialization/caller/table checks are pending |

The binaries' little-endian storage does not prove bit order in the transmitted
waveform. Diagnostic strings were enumerated as navigation evidence, not accepted
as field definitions. Later batches linked above execute bounded real prefix,
writer and variant-loader code in isolated emulation.

## Association inventory and first falsifiable check

The expanded catalog contains 195 JSON receipts across the signal-clustering,
sequence-semantics, all-track, DS10-extension and resumed-identity stages, plus
links to saved hierarchy arrays. This is an artifact inventory, **not 195 verified
associations**. The new coordinate ledger expands selected nested artifacts;
the exhaustive semantic review remains in progress. Historical receipts
that mention public reference data are catalogued for provenance; this experiment
uses only the saved DS7/DS8/DS9 track features.

Before matching cluster counts to firmware field widths, test whether the
partition is invariant to harmless input ordering. Use the saved 367-track
word-distribution and mean-word-bit hierarchies. Recompute average linkage from
saved features and require agreement with each saved tree. Then perform 99 seeded
input reorderings, restore the original observation identities and compare exact
2-, 4- and 8-group cuts using adjusted Rand agreement (ARI; 1 means unchanged).
No signal value, label or receiver changes. These are numerical robustness
controls, not independent observations or a statistical test of satellite identity.

| Hierarchy | Pair distances at maximum | Median ARI at 2/4/8 groups | Minimum ARI at 2/4/8 groups |
|---|---:|---|---|
| Observed-word distributions | 94.276% | 1 / 1 / 0.683 | 1 / 0.0015 / 0.532 |
| Mean-word-bit profiles | 0.0283% | 1 / 1 / 1 | 0.967 / 0.877 / 0.697 |

![Stability under input reordering](local/tie-stability.png)

The distribution tree has very sparse overlap and many distance ties. Some cuts
depend strongly on input order or numerical tie handling. A selected branch
therefore cannot establish a two-bit firmware enum or satellite class. The more
stable mean-bit tree still requires known-T-code, sample-count, receiver, session
and label controls before interpretation. Stability is necessary evidence for a
partition-based claim, not proof of a meaningful field. Exact-count cuts may
divide equal-height merges; no preferred number of groups was selected afterward.

## Reproduction and next work

```sh
uv run --no-project --with capstone --with pyelftools python reports/2026_09_29_firmware_cluster_reaudit/raw_audit.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/tie_audit.py
uv run --no-project --with capstone --with pyelftools --with unicorn --with numpy --with scipy --with matplotlib --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit
```

Focused tests cover address translation/BSS exclusion and label-invariant partition
agreement. The next batches must expand the association ledger, audit complete
packing/initialization paths and variants, and test specific firmware-linked
predictions with held-out data. No source-specific interpretation, new decoded
field or completion of the renewed objective is claimed here.
