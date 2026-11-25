# The DS30-0049 phase-guided verifier recovered six installed measurements

The interpolated phase produced **10 native accepts on 117 original candidate-empty queries**. Six matched the installed 20 ms signed CFO and arrival within 250 Hz and two physical samples. These six represent six of 34 original installed-positive misses, and include four of the seven installed-owned misses in each calibration arm. Three other accepts differed from the installed winner and one occurred on an installed-empty lane. The left-neighbor and quarter-period controls produced zero accepts. An installed-empty acceptance is a detector disagreement with no independent emission label. [Complete signed score](measurements/directed-replay-0049-ram-score.json) · [Verified waveform factors and clocks](measurements/directed-replay-0049-ram-waveforms.json.gz)

| Epoch supplied to the one-seed verifier | Gates | Fractional checks | Accepted | Matched installed | Matched installed owners per arm | Native CPU |
|---|---:|---:|---:|---:|---:|---:|
| Interpolated | 117 | 11 | 10 | 6 | 4 | 16.348 ms |
| Left donor | 117 | 1 | 0 | 0 | 0 | 7.814 ms |
| Quarter-period control | 117 | 0 | 0 | 0 | 0 | 6.939 ms |

Before waveform verification, five interpolated proposals already agreed within the signed tolerances. The verifier kept four of those matches, gained two and lost one, with no net increase in matched owners. It narrowed the signed carrier error from 422.2 to 21.7 Hz at one previously unmatched owned lane and from 344.2 to 99.7 Hz at one unowned lane. At the lost owner lane, error rose from 160.4 to 283.5 Hz. No broad search, extra seed, cancellation or local refinement ran. [Sealed timing and per-lane changes](measurements/directed-replay-0049-ram-run.json)

## Measured cost and admission

One child exhausted all six enrolled files and authenticated **384/384 ordered original windows**, including all unqueried windows. The ordinary reader checked the manifest, indexes, 468.49 MB of encoded waveform bytes, individual windows and the complete decoded member hashes. The authenticated sweep took **1.284 s wall and 1.276 CPU s**. The isolated process took **2.655 s wall through exit and 2.212 Python CPU s**, with 368.6 MiB peak RSS. The marginal interpolated verifier cost was **0.140 ms CPU per supplied lane**, including rejects. The three native paths together used 31.100 ms CPU. These are nested in the sweep clock. A receiver could use the marginal clock once an authenticated original window and a forecast are available. This replay charges no live buffering, proposal Graph, location fit or publication.

The successor for higher-priority DS30-0218 had remained deferred with its installed arm complete. The enclosing official deferral was 0.107 seconds old at dispatch. The child held the actual inherited Gauss lock, exited normally, and released the lease at most 2.769 seconds after the deferral, leaving **27.231 seconds** before its scheduled retry. The next official event, another storage deferral, was recorded 32.102 seconds after the first. The successor remained unstarted in the observed period. Only the preregistered official-deferral route ran. [Deferral admission and next-event audit](measurements/directed-replay-0049-ram-run.json)

All 13 exact scientific files remained fully resident before and after the child. The resident-source qualification passed. The original strict zero-input condition failed. The Python child reported 51,704 process input blocks, of which 1,976 occurred inside the timed sweep boundary. The separate wrapper reported 88 blocks. The capsule allowed the normal OS and release runtime, and the counters do not assign individual blocks to files. No backing archive, catalogue, additional capture, or numerical position solve was opened or run.

## Earlier attempts and no-waveform proof

Earlier admission attempts spent zero waveform or native calls. They recorded a held shared lease, a weighted bulk queue of 3.396 against the two-request limit, and another 300-second watch that expired. The capsule preflight mounted only the exact signed manifest, six compressed original members and six indexes from the private tmpfs stage. [Original replay history](empty-lane-directed-replay.md) · [RAM admission protocol](directed-replay-0049-ram-protocol.md) · [Initial preflight receipt](measurements/directed-replay-0049-ram-ready.json)

All 13 files were resident, with **469,531,245 logical bytes** and **469,565,440 resident page bytes**. The ordinary installed source verified the exact manifest in the no-waveform proof. The proof denied payload and index opens, loaded the byte-pinned directed DSO and pilot, and checked that a private inherited flock excluded independently opened lock descriptors and remained operative in the isolated child. The later timed admission uses the actual shared Gauss lock. The namespace denied all three socket families, backing, campaign and the physically staged but unenrolled seventh member. Private tmpfs scratch provides the runtime's writable output directory.

| CPU3 preflight | Wrapper elapsed | Python CPU | Wrapper input blocks | Python input blocks | Original waveform or index opens |
|---|---:|---:|---:|---:|---:|
| Instrumented first proof | 1.699 s | 1.058 s | 160 | 35,440 | 0 |
| Identical second proof | 1.309 s | 1.028 s | 24 | 5,776 | 0 |
| Final preflight | 1.493 s | 1.014 s | 168 | 39,776 | 0 |

An additional no-waveform trace observed 730 regular file opens in the allowed OS and release trees, covering 109.6 MB of distinct named files after deduplication. A privileged passive page census at a later instant found 661 files with at least one missing page and 78.2 MB of nonresident logical bytes. The census describes code-page exposure and does not assign individual process input blocks. Root-runtime reads remain charged and separately visible. The predeclared zero-process-input qualification stays distinct from the authorized resident-source scope, which requires unchanged fully resident scientific files immediately before and after launch and all original authenticating reads. Active swap prevents inferring uninterrupted residency from two checks alone.

The as-run CPU3 proof is sealed at SHA-256 `bfd399dad6a1bd8643509a9a0b67cf15681eede737b241881a4b2ef23e989a2a`. The deferral rule froze at `db69a2fbb` and the as-run code at `db8eedf15`. The decoded waveform receipt hashes to `567e033f2b0a6a44bc9fcf472d5870920a7123733478decf25e1c44109bcd599`. Fourteen focused tests passed. [As-run preflight](measurements/directed-replay-0049-ram-deferral-ready.json)
