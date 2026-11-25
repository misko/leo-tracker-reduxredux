# The next position-blind fast moment correction

The four-case enrollment remains open in its frozen order. No recording has been selected. All four recording metadata rows are complete. The current blockers concern authenticated catalogue custody. Neither case errors nor fix status, RF agreement, projected edits or survey entered the check. No replay or numerical slot was launched. [Frozen protocol](ds30-next-moment-fast-enrollment-protocol.md) · [Initial check](measurements/ds30-next-moment-enrollment-initial.json) · [Latest check](measurements/ds30-next-moment-enrollment-status.json)

| Execution rank | Recording | Position-blind status |
| ---: | --- | --- |
| 70 | DS30-0003 | Authenticated request and authority available. The signed cutoff is 1794549091515038880 ns and the archive digest is `sha256:6e1c98af94835640ec516da16a0a703329835b84ecd372755886e3878a9d8bf6`. The 19 available direct tmpfs donor directories contain 46 distinct causal filenames before that cutoff. No contiguous window reproduces the signed archive digest. Await a locally available exact catalogue manifest or completed official pair. |
| 71 | DS30-0036 | Original field request and archive authority pending. The existing 0036 scratch path contains no staged TLE catalogue. |
| 72 | DS30-0381 | Original field request and archive authority pending. |
| 73 | DS30-0370 | Original field request and archive authority pending. |

No rank has been excluded. A rank whose official pair completes may be excluded when its authenticated local roster and the documented resident donor search give no complete match. The selector keeps any completed-custody exclusion in subsequent signed checks. The first qualifying rank seals the enrollment even if its official role pair is still pending. Later results cannot select another case. The checks use only the frozen original input audit, compact official request and role-verification metadata, and bounded names in documented tmpfs directories. They open no original backing archive, TLE bodies, detector results, waveforms or surveys.

## Recheck and later prepare

Use a fresh ledger path when the official request, catalogue manifest or pair-verification metadata changes. `--rosters` can point to a local metadata directory containing an independently available exact `DS30-NNNN.json` basename-to-digest map. The map must match the authority’s original digest and cutoff. Leave that flag out if there is no such local map. Neither mode reads the original archive.

```bash
checkout=/srv/postgres-nvme/leo-ds30-research-worktrees/masked-cfo-next-two-entry
here="$checkout/reports/ALGO08/v3"
prior="$here/measurements/ds30-next-moment-enrollment-status.json"
next=/tmp/leo-ds30-next-moment-enrollment03.json
controller=(sudo -n -u leo taskset -c 3 nice -n15 ionice -c3)
"${controller[@]}" /usr/bin/python3 -IB "$here/ds30_next_moment_custody.py" "$next" \
  --previous "$prior" --previous-pin sha256:73a103e5384d17702babd361a1302531d524fcd6404c7e14a71187cb3c762743
```

After a ledger seals one eligible recording and both official roles verify, prepare the normal saved path using a fresh private `/tmp` root. Preparation rechecks that the authenticated saved detector and exact donor files are already resident. It budgets and verifies one common local archive copy, builds both cells on the same output medium and performs each role’s isolation, input and normal-entry checks without solving. The generic corrected worker uses the same released Graph scopes as the rank-68 adapter, derives the original held-odd mask and applies the unchanged moment projection online before the edited Graph. It seals its actual support and proof, including zero projected changes. The ordinary path has no correction scope. [Selector](ds30_next_moment_custody.py) · [Paired entry](ds30_next_moment_publication.py) · [Released Graph adapter](moment_preserving_fast_graph.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
run=/tmp/leo-ds30-next-moment-saved01
launch=("${controller[@]}" env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -IB "$here/ds30_next_moment_publication.py")
"${launch[@]}" prepare "$run" --enrollment "$enrolled_ledger" --pin "$enrollment_pin"
```

The following commands are the future numerical handoff. Launch only on separately authorized windows. The existing RAM-only capsule checks current official idle status, fresh deferral and the shared CPU2 lease. Ordinary must exit and seal exact parity with the official successor before corrected can start. Both verified publication outcomes must seal before geographic scoring. The entry retains a genuine withhold and its reason. A successful fix requires both calibration arms, 179 measured grid nodes, path, and eight verified PNGs. The worker wrapper records namespace launch through exit, in-namespace GNU `time` usage, full verified-publication clock, separate observer export, common staging and both role preload checks. These saved timings exclude raw acquisition.

```bash
"${launch[@]}" watch "$run" --cell ordinary --pin "$ready_pin" --driver-pid "$driver_pid"
"${launch[@]}" watch "$run" --cell corrected --pin "$ready_pin" --driver-pid "$driver_pid" \
  --ordinary-gate-pin "$ordinary_gate_pin"
"${launch[@]}" score "$run" --pin "$closure_pin" --ready-pin "$ready_pin"
```

Eighteen component and adjacent tests passed. The new tests used the actual released Graph ports on a synthetic detector fixture for both publication roles and exercised exact roster matching, both acquisition flags, frozen order and zero edits. A real two-role preflight awaits an enrolled source and verified official pair.
