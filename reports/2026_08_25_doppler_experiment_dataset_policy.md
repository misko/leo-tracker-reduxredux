# Dataset authority for the next Doppler experiments

Date: 2026-08-25 UTC

Status: **frozen input policy; experiments not launched**

This report freezes which existing recordings may be used for the six proposed
Doppler-rate experiments. It protects newer and in-progress collection by making
input authorization deny-by-default. The machine-readable authority is
[`doppler-experiment-dataset-policy-v1.json`](../config/analysis/doppler-experiment-dataset-policy-v1.json),
and the validator is
[`doppler_dataset_policy.py`](../src/leo/analysis/research/doppler_dataset_policy.py).

No raw IQ was opened and none of the six experiments was run while preparing
this policy. Only committed inventory rows and manifest metadata/digests were
used.

## 1. What this policy means

The cutoff is the existing capture
`cap-20260825T150802-473cb5bbcbd6`. A capture is denied if it is newer than that
cutoff, absent from the exact role allowlist, bound to a different recording or
analysis manifest, or selected through a dynamic operation such as `latest`, a
glob, directory enumeration, or a database query.

The policy also denies:

- all current and future experimental collection;
- every PRE-FIX counterless capture;
- the 3 MS/s and 5 MS/s `CAPTURE_ONLY` recordings;
- partial or fragmented raw recordings, in-progress or uncommitted captures, and
  cross-retune inputs;
- research-lane products not named by a later reviewed policy revision; and
- any substitution made after response data have been opened.

The POST-FIX classification follows the criteria in the
[refill-aware Doppler method review](2026_08_25_doppler_rate_and_satellite_linking_method_review.md):
device-counter authority, observed samples equal to device span, one continuity
segment, and zero missing/overflow/gap evidence. A report date is not sufficient.

The 24-hour inventory is frozen at repository commit
`857491483677870c244bbfe0cdff662648287971`, has 89 rows, and has SHA-256
`fb7c8ee55ebf14911b84c03a80a5a1d690efc74a9675b4e95191eb55e77fc1a9`.
Its construction and continuity findings are described in the
[post-refill retrospective](2026_08_25_post_refill_24h_retrospective/README.md).
The inventory binds the 30 Aug-25 captures in this policy. The six Aug-24
development captures predate that inventory and are separately enumerated in
the policy; their exact recording/analysis manifests are required at launch and
they are already published POST-FIX development inputs. Bounded partial analyzer
coverage, such as on `101428`, is not raw-recording loss and is permitted for
development when its sealed manifest is the exact policy binding.

## 2. Exact role allowlists

### 2.1 Holdout foundation: 15 captures, at least 10 evaluable

These captures are reserved for the response-blind feasibility and comparison
of fixed 500 ms, fixed 125 ms, and causal 20 ms estimators:

| Capture | Capture | Capture |
|---|---|---|
| `cap-20260825T010019-89c2889553e0` | `cap-20260825T015754-6bfe6b67b1be` | `cap-20260825T020035-c9413370f93b` |
| `cap-20260825T022235-0afd1298f096` | `cap-20260825T030000-49e936766343` | `cap-20260825T031245-4fbc260ab065` |
| `cap-20260825T031521-ec8adc0e9426` | `cap-20260825T033028-374381fbcd3a` | `cap-20260825T033302-80fddf217eb5` |
| `cap-20260825T034929-bc0480bdb4a8` | `cap-20260825T035201-d0abaead734c` | `cap-20260825T041207-a5f08ab5bd42` |
| `cap-20260825T043656-2da9e806d487` | `cap-20260825T050946-ab916a6d0eee` | `cap-20260825T051221-0032700e2140` |

Here, **protocol-unopened** has a narrow meaning: none of these recordings has
been scored by the six proposed experiments. They do already have committed
Standard products and appear in the descriptive 24-hour retrospective. This is
therefore a downstream-method holdout, not a claim that no one has ever examined
any product from the capture.

Episode feasibility may use counter metadata, the frozen upstream
source/epoch/alias product, and even-Qin evidence. Future odd-Qin errors and
candidate-method outputs may not select captures, episodes, branches, aliases,
or masks. At least ten evaluable captures must be frozen before scoring; all
failures stay in the ledger, and no replacement is allowed.

### 2.2 Opened development: 16 captures

These are available for implementation and parameter development only:

| Capture | Capture |
|---|---|
| `cap-20260824T192019-9023840c8e9f` | `cap-20260824T192252-9981b9c27853` |
| `cap-20260824T192531-491832825b97` | `cap-20260824T193733-1454b499b8bb` |
| `cap-20260824T194009-34ae34f129bc` | `cap-20260824T194245-1dfbc879df2b` |
| `cap-20260825T054455-47f684bbc3cc` | `cap-20260825T071530-b00e74ac23ee` |
| `cap-20260825T083906-9e15fac173f1` | `cap-20260825T101428-681b85cf4224` |
| `cap-20260825T115127-b61fef4673a4` | `cap-20260825T130425-1678069fefd1` |
| `cap-20260825T142817-9949c81ca994` | `cap-20260825T144823-4a812245fce1` |
| `cap-20260825T145100-cc48b00cfa28` | `cap-20260825T150802-473cb5bbcbd6` |

They may tune the causal `[CFO, rate, acceleration]` state, the weak-frame
likelihood gate, and V3/V4 implementation. They cannot provide new holdout
evidence.

### 2.3 Polynomial-phase injection: three opened hard-null backgrounds

- `cap-20260825T062228-886fe2dd9cde`
- `cap-20260825T105640-facdadeffb3b`
- `cap-20260825T111222-a2d4ce2afb9a`

Only deterministic, digest-verified spans from these published hard-null
captures may be used. Synthetic seeds and truth parameters must be frozen before
held-background scoring. Injecting into an active background requires a new
policy revision.

### 2.4 Multi-radio development: four opened captures

- `cap-20260825T065355-ba3e4fb8857b`
- `cap-20260825T103607-9bd90a1a50e4`
- `cap-20260825T130425-1678069fefd1`
- `cap-20260825T150802-473cb5bbcbd6`

The exact same-emitter overlap, radio/receiver path, source branch, and alias
must be frozen before fitting. Separate constant CFO offsets are allowed; the
primary model may not silently add a separate drift for every radio.

### 2.5 V3/V4 canary

`cap-20260825T150802-473cb5bbcbd6` is the sole opened canary. It is useful for
implementation regression, but it cannot support a new V3/V4 accuracy claim.

## 3. Mapping the six experiments to the policy

| Proposed experiment | Permitted first stage | What must happen before evaluation |
|---|---|---|
| Fixed 500/125/20 ms comparison | `holdout_foundation` feasibility only | Freeze a derived manifest with at least ten supported captures, exact episodes, branches, aliases, masks, and failures; commit it before odd-Qin scoring |
| Polynomial-phase injection | `polynomial_injection` | Freeze spans, seeds, truth grid, occupancy, aliases, steps, sample-clock offsets, and scoring rules |
| Causal `[CFO, rate, acceleration]` state | `rate_development` | Freeze dynamics and hysteresis on opened data, then evaluate unchanged on the derived holdout manifest |
| V3/V4 downstream rate | `v3_v4_canary` | Freeze implementation and identical-frame metric, then evaluate unchanged on the derived holdout manifest |
| Multi-radio common-rate/free-offset | `multi_radio` | Freeze same-emitter overlap and path bindings; use no holdout-foundation capture in development |
| Gated full likelihood | `rate_development` | Freeze the past-only ambiguity gate on opened data; any holdout use must be named in the derived manifest before scoring |

This deliberately prevents parallel agents from independently choosing
convenient recordings. Parallel execution becomes safe only after each
experiment has a committed protocol derived from this common authority.

## 4. Enforcement

The validator performs strict JSON/schema checking, rejects duplicate keys,
checks the capture cutoff and role-specific provenance, verifies the frozen
inventory bytes and its Standard bindings, and provides manifest-byte
authorization against the exact recording and analysis hashes. It rejects
duplicate consumed inputs. A separate final disposition ledger retains every
capture, records explicit non-evaluable reasons, and enforces each role's
minimum evaluable count.

The component tests in
[`test_doppler_dataset_policy.py`](../tests/analysis/test_doppler_dataset_policy.py)
cover the committed policy, inventory bindings, new/unlisted captures, role
confusion, digest drift, byte drift, duplicate ledgers, insufficient holdout
size, and malformed policy revisions.

This is the capture-level safety layer. Episode/source/alias/mask choices are
experiment-specific and must be captured by the next committed derived
manifest; prose constraints alone are not permission to open or score an
alternative input.

## 5. Launch gate

The experiments remain **not launched**. Before any agent is dispatched:

1. commit the protocol-specific derived manifest;
2. validate the frozen inventory and actual manifest bytes, then obtain IQ only
   through a digest-pinned recording reader;
3. record the exact policy commit in every output;
4. refuse dynamic discovery and any capture substitution;
5. retain every non-evaluable capture in the failure ledger; and
6. keep figures and reports conditional on the exact consumed-input ledger.

Only a reviewed policy revision can add a capture, change a role, or authorize
data collected after `150802`.
