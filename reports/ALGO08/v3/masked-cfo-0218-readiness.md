# DS30-0218 integrated masked CFO saved entry

The saved position wrapper now invokes the frozen masked CFO feature at
the installed application's ordinary `prepare_tracks` boundary. It
derives once from the original authenticated sparse detector packet and
the actual approved TrackConfig. It substitutes only the continuous CFO
in the matching winning-observation rows. Original detector bytes,
fixture timing, signed receiver identity, RF, margin, timestamps and row
order remain intact. The ordinary Graph receives the edited rows and
rebuilds tracks. The masked released Graph has its own counters and does
not enter the ordinary Graph's optimization counters. The feature and
overlay run inside the corrected saved worker's clock.
[Frozen enrollment](masked-cfo-next-original.md) · [Integration protocol](masked-cfo-next-original-protocol.md)

The DS30-0019 integration probe came through the real saved publisher on
CPU3 and stopped at the ordinary Graph return. It changed 366 CFOs among
4,996 winning rows while publishing the original detector bytes. The
corrected rows match the prior independent feature receipt byte for byte
under the canonical encoding. The masked Graph assigned 1,701 rows across
83 tracks and the ordinary rebuilt Graph assigned 3,645 across 120.
The probe recorded 0.633 s for derive and 0.00085 s for the overlay.
The actual boundary for these diagnostic clocks was Graph preparation.
It reached no orbit preparation, position solver, terminal, grid, path
or figure. Six focused tests passed, including unchanged zero-edit rows,
withholding before and after Graph, approved-config rejection and a
second same-packet Graph preparation. The saved wrapper never loads the
historical forecast file.
[Probe ledger](measurements/masked-cfo-0218-readiness.json) · [Feature binding](masked_cfo_saved.py)

At 01:15:53 UTC on 2026-11-25, both authenticated original field roles
were pending without attempts. DS30-0218 is the 65th case in execution
order after moving the two smoke cases to the front. Its recorded
assigned rank is 63. The case remains fixed. The actual DS30-0218
catalogue has yet to be verified because its signed field result is
unavailable. The prepared metadata binder accepts only a unique
complete digest-and-cutoff match from verified resident tmpfs donors.
It checks every selected body before staging same-volume links.

Run the following from this research checkout with the release Python.
The status check reads the frozen campaign plan and its two current
authoritative role rows. Preparation requires the verified pair
receipt and matching attempt digests, including a genuine withhold
where applicable. A failed or missing role remains visible in status.

```bash
python -IB reports/ALGO08/v3/masked_cfo_0218.py status
python -IB reports/ALGO08/v3/masked_cfo_0218.py prepare-field /dev/shm/NEW-0218-POSITION-STAGE
```

After the original pair verifies and the shared numerical slot is
separately authorized, the saved entry accepts `ordinary` or
`corrected` with the corresponding prepared cell directory, plan
`--pin` and inherited `--lease-fd` from the authorized saved capsule.
The worker checks the real benchmark descriptor. Run ordinary first.
The [scientific comparator](masked_cfo_0218_score.py) takes a sealed
JSON map keyed by cell, with the plan, through-exit clock, observation
witness and original solver receipt SHA-256 values. It verifies the
archived raw ordinary parity, including field source, numerical Graph
counters, owner order, grid/path, and figures where applicable.
With both exit-zero cells sealed, it opens the held reference and
reports both calibration arms on their actual support. This handoff
opens no auxiliary watch while the original field roles are pending.
