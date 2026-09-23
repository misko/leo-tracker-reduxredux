# Independent pre-outcome source and freeze review

Reviewed while the final-TEST export/baseline chain was live. This review read
only protocol, freeze, selection-freeze, metadata split membership, and source
files. It did not inspect TEST inputs, cache contents, baseline/timing output,
or numerical TEST outcomes; it did not start, restart, or interrupt a process.

The frozen rule is internally consistent: exact manifest TEST membership is 64
sessions in the Sep 22 00Z group, disjoint from TRAIN and validation. The
selected validation rule is global epoch at 0.2 s, with only the original
Sacramento 250 km and Reno 500 km priors and nested 1/6/16/64 views. The
sources restrict timing to a single global 0.2 s arm, and baseline inference
uses `held=False` and no reference values. Evaluation is the first source path
that requests complementary rows or a reference error, after checking baseline
and timing seals. The freeze binds the published validation selection digest
`ef36be4d8c739eea59c0f2a0b076ac847d4650cbee78bd4d06e124f5da1a5aff`.

Reviewed hashes:

| File | SHA-256 |
| --- | --- |
| `PROTOCOL.md` | `e58156edfb4b66ffde1b8c20e6b64abbe85eae9024e264287b88d1900ba68395` |
| `freeze.json` | `9948bb508d1bc170a04f2d51b8e3d4412e3867df077c61f346ecd85d60f3387e` |
| `selection_freeze.json` | `cad59db741783e8db8f8093b8f16327792d97a4a95c58a3cd445cf51c46e9a5d` |
| `export.py` | `2090f5c103ca53cd5b9df6bb0f0a730f3a768b133bedb7d5cc661af456de18ad` |
| `baseline.py` | `4498d634e08b0a7ea7c8f3753522118a9a2732b5e258bbf670c4088e995c85d3` |
| `timing.py` | `4d63beb648c2261b6b09374fc27db1b490cd021f46fc156ab7f07773c96cfee0` |
| `evaluate.py` | `507ae98f07f650f2b2f38c3c241947f59e96f32c4f164ce3a7134a0c6168cc03` |

One actionable provenance defect was reported before outcome evaluation:
`evaluate.py` verifies baseline and timing seals but does not reverify every
cache receipt and NPZ digest from `cache_receipts.json` before post-seal TEST
held/reference scoring. Timing inference also does not bind those cache
digests. A mutable local cache could therefore change after the training seals
and before evaluation without a detection or result binding. This differs from
the frozen-validation evaluator and falls short of the protocol's cache-hash
verification requirement. Resolve and refreeze the affected source before
final outcome evaluation.

## Execution amendment review

The initial exact-64 export then failed before any baseline, timing fit, or
outcome evaluation: frozen session 48,
`scan-hop-6cd2560365a058bc`, lacks complete counter-continuity authority.
The receipt manifest contains 63 verified exports and this one recorded
failure. The frozen 1, 6, and 16-session prefixes end before that ID; the
complete 64-session view does not.

I reviewed `execution_amendment.json` (SHA-256
`80c8f7b03e696c7c4285da3da22377443042d6dd35ea2be8faeca7e8a2f46f6a`). It
retains the immutable freeze and selects no new configuration. It binds the
receipt manifest digest, the failed ID and position, and the superseded plus
amended execution sources. The amended baseline, timing, and evaluator hashes
are `a2dbf969553b3f94abb9e926c632df1b29bae6abbdb82a92b141f82110fd1052`,
`1d5812e9e6362b1ceaf4d9d35910ccb703af87593a5316fa3e76ed8b00e270c6`, and
`d5d04d0fba11f8f733310e6f05e1e258d602fdecab31b9c33a655c7d7596e97d`.

The amended code verifies the fixed receipt manifest and cache hashes, emits
six successful fixed-prefix prior arms and two explicit 64-session failures,
then preserves those failures through timing and outcome rows. It does not
drop, replace, filter, or reorder a session. `py_compile` and Ruff passed for
the three amended sources. Any resulting 1/6/16 rows are predeclared partial
views only. The complete 64-session TEST evaluation remains failed and
ineligible for a final claim.
