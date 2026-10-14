# DS22 authority and the dataset consumer boundary

The new `tools/ds22_fitted_inventory.py` freezes DS22 membership and roles using
only standard-library metadata reads. Its trusted manifest digest is
`705380facbea54e6a1142eab07f1114f7ae99d3066e4f8bd9210cb55014768f3`.
The original authority is
`/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_14_ds22_post_ds21/local`.
Neither that authority nor DS21 is modified.

All 137 recordings remain in the inventory. The primary CH1–8 cohort has
69 fast acquisitions and 68 pinned tracking inputs. DS22-137 remains eligible
with a null session ID and unavailable input; it is an explicit missing result,
not a filtered recording. Eligibility uses recording format and acquired
channels, never a session-name prefix or analysis success. The 68 adaptive
recordings remain visible but are outside this eight-channel numerical protocol.
No claim of model coverage on all 137 follows from completing the primary cohort.

Before any DS22 error is read, seed **20261014** randomizes all **35 whole UTC
acquisition hours**, including both recording formats. The first 12 shuffled
hours are locked evaluation. This gives 89 development/48 evaluation members
overall; the fast cohort has **45 development and 24 evaluation**, with
**44 development inputs available plus DS22-137 unavailable**. All 24 evaluation
inputs are available. Nearby fast/adaptive acquisitions retain one common role.
Hour grouping does not establish independent hardware or orbital errors.

The inventory checks the published manifest digest and its seal entry, exact
evaluation-unit membership, every pinned tracking snapshot, and the existing
tracking adapter bytes. It does not claim to rehash all 1,169 files in the mint
seal or any IQ payload. It archives its own tool and the adapter, and read-only
verification reconstructs roles and metadata exactly. Creation requires a new
exclusive output directory; verification never repairs an archive.

The adapter is explicitly pinned to the same source used by DS21:
`/opt/leo-fast-auto/20261011-r3/bin/fast_scan_standard_pipeline.py`, digest
`b1e7d7072877535f20a5becbb18eaa39416464577e84af5c315122cc3f1d20a9`.
The 250 km regional prior retains the existing latitude/longitude/altitude
constants. No reference file is read to construct it. Native tracking session
IDs can differ from acquisition labels; the raw-content/input bindings carry
the identity, not guessed session-name equality.

## Genuine preparation provider

`tools/ds22_fitted_provider.py` supplies new `freeze`, `run`, `read_case` and
`load_training` ports. Its schema is explicitly
`ds22-fitted-training-provider-v1`. It refuses locked members, ineligible formats
and unavailable inputs before loading observations. There is no switch to open
locked inference in this development provider.

Freeze binds the actual DS22 inventory/member/input, inherited numerical source
closure and the new provider source, before preparation. Run claims a durable
attempt and uses the original counter-only whole-block partition (seed
20261012, 20-second blocks). Only training probes are projected, separately for
all/low/high views. Neither held nor quarantined probes enter preparation.
The loader preserves original timing/counter metadata. A causal TLE snapshot
is pinned after preparation; no orbit is propagated and no optimizer is called.
Preparation retains the **60/75/80-second internal/TERM/KILL** bounds. Failed
or orphan attempts cannot automatically retry.

The completed port exposes original numerical objects and metadata through a
genuine DS22 case record. It includes training evidence, frames, partition,
clock nodes, causal TLE binding, native session metadata and original source
authority. `load_training` reconstructs and checks the same prepared evidence
inside the future consumer's bounded slice. Cached `read_case` validates
metadata without projecting observations again.

The provider calls existing mathematical preparation functions explicitly. It
does not change `ds21_fitted_initialization.inventory`, monkeypatch a module,
remove DS22-137 from membership, or write a false DS21 protocol. The existing
DS21 case/stage validators remain inappropriate for DS22 and must not be
bypassed by relabeling the new record.

The first authorized development preparation, DS22-001, completed in
23.928574 seconds under this policy. All/low/high contain 3,229/1,811/1,418
training windows and 24/24/23 tracks; held block identifiers are 1, 3 and 7.
The 404-source closure and causal catalogue are pinned. There were zero orbit
or optimizer calls, held projections and reference accesses. Preparation
terminal SHA-256:
`ca012aea3c5210ec23674bd814f40281a54ffbe77a147d9e8859ccc51ca70aae`.

## Narrow discovery consumer and remaining stages

`tools/ds22_fitted_discovery.py` now implements the first consumer. Its
`ds22-fitted-discovery-v1` schema binds the genuine provider and delegates to
the existing discovery mathematical port, without calling a DS21 case reader.
This is the original baseline grid (100/50/25/12.5 km, 100 scored points), not
the later coverage-policy variant. It retains all three training views and
the original training-only candidate selector, bank and point validators.
The discovery slice is bounded to 480/495/500 seconds. Numbered clean
checkpoints need explicit continuation; failures and orphan claims cannot
automatically retry. A read-only stage port exposes the exact selected bank
and proposals for later DS22 stages.

Twelve owned discovery tests pass, including actual synthetic bank loading,
the real cached-point hierarchy/selection replay and real slice/point
validators. Rebinding file digests does not admit a changed selector, an orphan
slice or an out-of-bounds fitted c. This qualification uses zero new fits.

The remaining five-stage DS22 facade must own its `freeze_stage`, `context`, `read_stage`
and bounded run functions. Its predecessor reader uses this provider for the
first stage, then its own sealed stage outputs. Existing numerical ports such
as `operation`, `stage_proposals`, `assemble`, candidate-bank propagation and
physical seed encoding can be reused with explicit in-memory payloads. It
must retain the same per-call limits and archive the exact composed sources.
No general plugin framework or modification to a live DS21 closure is needed.

Implement the five stages in a new `tools/ds22_fitted_initialization.py`:

| Stage | Genuine predecessor | Existing numerical ports | Internal slice limit |
|---|---|---|---:|
| shape | DS22 discovery `read_stage` | `stage_proposals`, `operation`, `assemble` | 240 s |
| shape-bootstrap | DS22 shape reader | same ports, original bootstrap and candidate union | 90 s |
| hybrid | DS22 shape-bootstrap reader | same ports, original physical seeds and fitter | 240 s |
| cold-bootstrap | DS22 hybrid reader | same ports, fixed-pool bootstrap | 90 s |
| six-proposals | DS22 cold-bootstrap reader | original six physical exports/encoding | 90 s |

Each stage freezes the exact predecessor's authority and the provider's five
case/preparation bindings, all prepared frames/partition/TLE fields, ordered
candidate indices, bank extent and declared proposals. The public protocol is
DS22-specific; `parent["original"]` is merely the private in-memory payload
expected by mathematical helpers, not a fabricated historical receipt. Shape
still has three view calls containing three starts each; bootstrap/hybrid
stages retain their declared original call identities. Read-only bootstrap
receipt reconstruction must not call a helper that writes aggregate receipts.

The new stage reader should reuse value/layout checks and independently replay
candidate unions, six-proposal ordering, physical exports and own-source
closure from bound calls. It must check every call launch/result/termination,
outer numbered slice and terminal artifact before exposing a parent. A cached
terminal must not reconstruct observations or fit again. Tests should cover
all five predecessor transitions and compare the actual operation arguments
with the inherited mathematical ports, including a synthetic six-proposal
export/closure replay. Freeze the new composed source closure only after these
tests and independent review; leave the already frozen provider/discovery bytes
unchanged.

The subsequent A/B/C consumer also needs its own DS22 authority reader. The
existing DS21 model wrappers cannot be pointed at a DS22 parent merely because
the vector layouts match. Preserve the original twelve units/54-call ceiling,
exact physical transfer and metadata compatibility rules behind that new
reader. Development errors and held scoring remain unavailable until all
required model outcomes and the training selector are sealed.

Before executing a consumer, require component tests for genuine DS22 authority
and locked refusal, partial/failed/orphan claims, exact parent membership and
source bindings, source-function transport, cached completion without refits,
and strict separation of post-seal evaluation. A compatible case payload alone
does not establish that the full six-stage initializer or A/B/C model consumer
has been implemented or qualified.

## Independent half-only controls

The preparation provider's three views are a baseline input port, not the final
independent-half experiment. Historical half estimates shared candidate
discovery, initialization geography and some receiver lifts from all channels.
Those results must remain labeled as conditional shared-proposal controls.

For the final requested comparison, a separately frozen view-local initializer
must build each half's candidates, geographic starts, calibration exports and
receiver lifts exclusively from its permitted training channels. Counter-only
block assignments and capture-time metadata may be common; other-band CFOs,
shape winners, discovered identities and fitted corrections may not enter a
half-only initializer. Bind the allowed channels into every stage protocol and
test rejected cross-band donor inputs explicitly.

Use a declared common six-start policy for each standalone pipeline, rather
than pretending that the existing three shape-view winners still exist after
one band is removed. One candidate recipe is three separated cold proposals
plus shape refinements of those same three proposals. Its budgets and selector
must be frozen before results; this recipe is not yet implemented or selected.
For Model A, a single-band control is its standalone band-fit component; the
low-to-high transfer stage is undefined when the other band is absent. Name
that comparator explicitly rather than inventing an A high-band transfer.

Evaluate one frozen algorithm per model, retaining all failures. Report DS21
and DS22 separately, development and locked cohorts separately, and all/low/high
errors on matched recordings. The targets are error below 1 km, median below
0.5 km, and combined error no worse than either standalone half. Shared-proposal
halves and independently initialized halves must never be pooled under one
histogram label. Unavailable outcomes stay in coverage/pass denominators; they
must not disappear because a numeric-error histogram cannot bin them.
