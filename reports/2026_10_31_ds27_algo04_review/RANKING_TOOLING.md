# DS27 residual fragment ranking

The approved primary ranking uses contiguous **native source fragments**, not
the span of an entire joined graph track. It subtracts the chosen ALGO04 fitted-c
published owners, tracing ALGO03/ALGO02 fallback exactly. It splits at a claimed
source point, an existing polynomial-piece boundary or an adjacent gap greater
than **5 seconds**. Duration is the first-to-last observed point interval;
interpolation never contributes duration. Parent residual span/max-gap and
2/10-second continuity sensitivity are retained.

Identical physical-ID graph/alias variants collapse. Partial overlaps, repeated
physical recordings, duplicate native IDs and changed source hashes stop the
ranking rather than double-count evidence. Every fragment retains its parent
track index/key/ID, native indices, full original IDs, exact residual IDs and
piece mapping. An optional `identities` array in the analysis index reproduces
the original recovery inventory TID. Without it, the parent ID uses the terminal
session identity; the full source-ID mapping still supports exact lookup.

`analysis-index.json` is supplied after all final ALGO04 outputs are frozen.
It contains `cases` with the required fields in `ranking-protocol.json`.
Unavailable cases remain in the denominator and are not mislabeled as
post-ALGO04 unassociated observations. Unassociated original GLRT winners outside
the graph are counted separately; no exhaustive discovery of untracked curves
is claimed.

```bash
cd /srv/bulk/leo/research/ds27-algo04-20261031
python3 -m unittest -q test_rank_native_residuals.py
OPENBLAS_NUM_THREADS=1 /srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python \
  rank_native_residuals.py --index analysis-index.json --output residual-ranking --plots
```

Outputs include the exhaustive JSON inventory, top-ten JSON/CSV, full fragment
CSV and per-scan counts. Context figures show every original GLRT point in both
receivers/all channels for each ranked parent scan: associated gray, residual
graph crimson and residual untracked orange. Each top-ten zoom shows its exact
points and existing source polynomial, plus point-minus-polynomial residual if
available. Native alias lifts and wraps are audited; polynomial lines break at
wraps. Existing graph polynomials are descriptive fits, not satellite evidence.

Nineteen tests pass across the ranking and retained-annotation tools, including chosen-proof selection, partially claimed tracks,
5-second continuity, piece joins, alias deduplication, overlap rejection,
untracked counts, source-hash binding and end-to-end duration ranking. No fit,
GPS, TLE or IQ read is part of the tool.

ALGO02 fallback owner IDs always come from published V1 gates. When the embedded
ALGO03 source-support proof is present, its owner labels are accepted only if its
ID set exactly equals those V1 IDs, every NORAD label is known, and every label
already present in V1 agrees. This supplies missing linear-gate labels without
adding unpublished replay memberships. Both arms were verified for DS27-0008,
0012 and 0014: ID sets stay equal and respectively 579, 369 and 467 previously
unlabeled memberships receive their saved source-proof labels.

The prior DS26 three-scan fixture was exercised before DS27 results existed:
167 residual fragments, 1,601 untracked residual points, 16 PNGs and ten PDFs in
7.89 seconds. The output is explicitly marked `fixture_only` and uses old
published ALGO03 support. DS26-0265 retains its 88.2606-second/120-point fragment;
DS26-0223's old 86.1903-second joined span becomes a 50.3711-second/58-point
longest native-piece fragment under the approved definition. Context and zoom
figures were visually inspected. This validates tooling and definitions, not a
DS27 scientific outcome.

The primary `top10.csv` ranks contiguous fragments. `parent-top10.csv` and
`parent_tracks.csv` provide a separate one-row-per-native-parent ranking by
remaining first-to-last span, explicitly retaining max gaps, piece count and
longest contiguous native fragment. The 5×2 `top10-overview.png` displays all
primary fragments together. Failed scans with retained native graphs have a
separate inventory and longest-three figure labeled **ownership unknown**;
they never enter the post-ALGO04 ranking with an assumed zero-owned mask.

`plot-inputs.json.gz` contains only the native observations, source tracks,
published owner IDs and exact top-ten IDs/aliases needed for the context,
polynomial and overview plots. It uses deterministic gzip with zero mtime and
has no local source paths, orbital arrays or geographic truth. Re-render it
without the original study paths:

```bash
OPENBLAS_NUM_THREADS=1 /srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python \
  rank_native_residuals.py --packet residual-ranking/plot-inputs.json.gz \
  --output portable-native-figures
```

Retained nomination/gate evidence is extracted without new scientific fits:

```bash
OPENBLAS_NUM_THREADS=1 /srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python \
  audit_top_fragments.py --index analysis-index.json \
  --ranking residual-ranking/top10.json --output top10-annotation-audit --plots
```

Optional per-case `algo03_recovery_path`/`algo04_recovery_path` index fields name
the retained original/replay roots. Matching uses exact parent, subset or bundle
source IDs, not suffixes of RX/CH names or hashes alone. The extractor preserves
recorded random-group votes, per-arm held RMS, phase convergence, visibility,
boundary mass, inclusion gates and negative exact replay slacks. Stored held
residuals plot only when native order and recorded held indices/blocks agree.
Shared-family diagnostics keep raw CFO-minus-prediction residual separate from
bias-removed residual and profiled RMS. NORAD entries remain hypotheses.

Missing annotations are attributed to budget only with explicit stage evidence.
The extractor also compares inventory proposed memberships with actual published
owners and `publication_support.unreported_postfit_ids`; shadow-only unpublished
IDs that suppress an inventory row are a distinct omission cause. An owner is
never borrowed from a similarly named component or neighboring published IDs.
The compact audit JSON and a deterministic `annotation-plot-inputs.json.gz` retain
exact plotted vectors without orbit arrays. The latter can be rendered with
`audit_top_fragments.py --packet ... --output ...`.

`audit_parent_extras.py --index analysis-index.json --inventory
residual-ranking/inventory.json --output parent-extra-audit` handles the two
parent-top-ten sources absent the primary top ten. Its rows explicitly retain
all remaining parent IDs and gaps, with no contiguous-duration claim. It reuses
the exact-ID audit and saves dedicated native/polynomial and held-residual
figures plus a standalone `parent-plot-inputs.json.gz` replayable with the same
script's `--packet` option. Two additional tests cover parent ID/gap preservation
and standalone owner-proof restoration; 21 component tests pass overall.
