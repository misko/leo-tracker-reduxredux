# Six paired word observations in two conditional DS8 revisits

Two previously unexamined visits conditionally associated with STARLINK-35850
yield **six independently receiver-checked 60-bit word observations**, each an
exact member of the already known repeating family. Their state indices differ.
This expands recovered observations but does not reveal a new field or establish
an RF satellite ID.

## Source and pairing

Both visits belong to DS8-F017 / `scan-fw-4458a753c0831235`, upper edge,
channel 1: visit 17 was selected from original census track T0001 (RX0), and
visit 74 from T0000 (RX1). Both tracks have the same retained conditional
Doppler label. Neither `(session, visit)` appears in the earlier signal inventory.
That inventory check is not a claim about every file ever generated in the project.

The census observation support centers are approximately **7.70135 seconds**
apart. These are two visits within one encounter, not separate orbital passes.
The candidate identity is a geometric hypothesis, not a verified same-satellite
transmission. Acquisition parameters and timing are retained for both receivers.

The unchanged decoder recovers the first 120 ms from each existing visit,
using the earlier exact source candidate and a timing-compatible peer selected
by acquisition margin. Manifest hashes, raw excerpt hashes, and common
valid-start counters are checked. The 89-frame paired outputs are separately
calibrated; the earlier census is preserved.

Visit 17 has one jointly pilot-qualified evaluation frame, and visit 74 has six.
Each exceeds 0.5 held-pilot coherence on both receivers. The existing 32-symbol
known-pattern compatibility assay passes all seven frames. A stricter test
then independently recovers words on **each receiver** over symbols 194–257:
full 60-slot coverage, even/odd word equality, normalized score >0.25, and
superiority to shuffled-code controls. Both receivers must accept and agree on
the entire 60-bit string. Six of the seven frames pass this stricter check.

| Visit | Local frame | Exact known-family state |
|---|---:|---:|
| 17 | 30 | 48 |
| 74 | 14 | 36 |
| 74 | 41 | 20 |
| 74 | 53 | 28 |
| 74 | 59 | 44 |
| 74 | 62 | 6 |

Visit 74 frame 47 fails the strict paired-word rule and is retained as a failure.
State numbers index the existing generator; they are not satellite numbers or
newly interpreted protocol fields. No bits were changed to force a known-family
match: generator membership is checked after word acceptance.

## Meaning and limits

The repeated candidate label is associated with multiple pattern states in a
single short encounter. This is consistent with the existing evidence that
the raw 60-bit pattern is not a fixed satellite identifier. It does not explain
what selects the pattern state or validate the geometric satellite label.

The six strings contain 360 observed sign positions, but not 360 independent
information bits: every string lies in the same known 60-state family. No FEC,
CRC, message framing, timing, position, or satellite-address field is recovered.
Receiver agreement remains vulnerable to shared model errors.

Neither visit reaches the existing minimum of 12 jointly qualified frames for
the discovery/evaluation changing-header assay. That assay abstains; these
results do not corroborate new unknown header signs. The two visits are not
pooled as if they shared a stationary header or one calibration.

## Artifacts and checks

`ds8_repeat_words.py` verifies the saved data-only cache hashes, runs the existing
word decoder independently per receiver, and stores both raw word strings,
acceptance flags, scores, and source hashes in ignored
`local/paired-ds8-DS8-F017-v74/paired-word-check.json`. Both visits' soft arrays
and recovery receipts remain in their respective ignored paired-ds8 folders.
All 37 relevant tests and Ruff checks pass. Both bounded recovery runs completed
without RF collection, downloads, commits, or deployment.
