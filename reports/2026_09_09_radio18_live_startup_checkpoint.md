# Radio18 live scanner qualification and startup correction

2026-09-09. Work-in-progress checkpoint. This is not a remote merge,
production deployment, or a declaration that adaptive detection is qualified.

## Scope

Only physically USB-attested serial `1040007c4a94000211000b009186843ef2`
at Ethernet `192.168.1.18` is used. USB port is `3-11`; radio traffic uses
Ethernet. PPU's shared serial lock, exact local/remote identity, idle buffers,
absence of competing clients, strict task-specific SSH pin, bundle hashes and
release-local host runtime are checked. `.14` and production radios are not
contacted. Installed iiOD is restored and checked after each owned canary.

The prior authorized maintenance restored released v0.49 and two receivers;
see [its checkpoint](2026_09_09_radio18_v49_2r2t_checkpoint.md).
**This startup correction changes userspace only**, not firmware, kernel,
FPGA or bootloader. The scanner still records both RX and classifies only RX1.

The authorized matrix is six nominal 300-second captures. Diagnostic RF also
counts toward its 30-minute limit; a request to extend the allowance is not
itself approval. Runs are immediate canaries with cadence-slot labels, not
claims of scheduled production execution. No production service is restarted.

## First live baseline

The original protected bundle, detector disabled, completed at 2.5 MS/s:

| Measurement | Result |
| --- | ---: |
| Source-counter span | 300.116398 s |
| Complete dual-RX visits | 2,387 |
| Retained valid IQ time | 286.440 s |
| Valid duty | 95.4429% |
| Missing samples / overflow / hop-event gaps | 0 / 0 / 0 |
| Mean retune, excluding startup | 4.31787 ms |
| Mean scheduler lateness, excluding startup | 0.41165 ms |
| Configured post-retune guard | 1.000 ms |

Session `scan-hop-58dbfc3f396cd056` has sealed manifest
`sha256:cb56692f40909f9fffa38289e205e51699215e31f8b8a479008a688862bb3029`.
Every retained compressed IQ object was reread and verified. The actual scanner
history route returned this recording; disabled GLRT correctly returned 404.
This is an ASGI check against the actual stores, not a deployed browser check.

Settings match the deployed scanner: 120 ms valid dwells, 1 ms guard,
131,072-sample blocks, eight kernel buffers, eight read-ahead visits,
64-visit storage queue, manual gain 40 dB, and rate-specific bandwidth/IF.

## Failure and measured cause

The first detector-enabled attempt failed before publishing a complete scan:
the first declared valid dwell started before the first IQ frame delivered to
the host. Two bounded diagnostic reproductions measured missing prefixes of
28,057 samples (11.2228 ms) and 11,277 samples (4.5108 ms), respectively.
Later frames were contiguous. These are real coverage failures, not a reason
to discard validation or silently pad samples. All owned processes and volatile
companions were cleaned up, and stock service/buffer readback was verified.

The provider started the hop scheduler when opening the buffer, before knowing
that an IQ frame could actually be accepted. The fix arms the existing state
machine at buffer-open and starts hopping once, at the first usable frame.
An unusable/discarded initial frame does not start it; cancellation before that
frame never starts it. The observed logs do not establish gain-sampler discard
as the specific cause, so no such attribution is made.

One separate 12.732204-second cancelled diagnostic preserved valid IQ at
94.2491% duty but emitted an explicit GLRT publication error: the fixed-hop
receipt lists retained complete visits while the detector inventory includes
a started partial final visit. No missing classification is converted into a
negative. That cancellation publication limitation remains open; the fixed V1
contract has not been relaxed. Adaptive binding separately accounts for started
events and bounds actual searches by delivered source IQ.

## Implementation and desktop verification

- libiio `a427e170b5a659b72b5177e058f01a17de6f4654`: deferred first-frame
  activation and provider/session tests. The new provider test first failed
  against the prior implementation, then passed with the correction.
- PPU `1460291`: bounded coverage diagnostics with component tests; incomplete
  IQ remains rejected. Its selected persistent-hop tests pass (51 tests).
- Actual provider tests cover both rates, detector off/on, fixed/adaptive,
  skipped first frame, cancellation before IQ, worker failure and pressure.
- Production TCP/provider/host/store/API regression: **28 tests pass**, including
  four full 300-second simulated source spans and cancellation cases.
- Installed host runtime/lifecycle regression: **57 tests pass**.

The first TCP test invocation accidentally imported ambient system libiio and
failed at setup. The corrected invocation calls PPU's public metadata-runtime
verifier before importing IIO; it retains exact-path/hash checks. No global
loader override, test skip or relaxed expectation was introduced.

The rebuilt nine-payload ARM bundle totals 3,467,936 bytes. Its identities are:

| Item | SHA-256 |
| --- | --- |
| Bundle manifest | `8b06b2246c090f0776de1f220a8eab9371a8f6ab25dae6a038247052cf3df8f9` |
| Algorithm/build | `04e8099570e0224633eeb0c513de7acc76a5f42e56b3eb000bbfb88dcb95a7bf` |
| Configuration | `b34276d4c9308155a4c78868d2b7807b1612e6a72d18b8f509451759ecc5152a` |
| iiOD executable | `4430ac29513d585fc60573851a1875bd774c39976f5249c64ccc1c77260166bc` |

The numerical settings are unchanged; the build identity changes with provider
source and private runtime paths. Previous scientific qualification is not
silently relabeled as an independent evaluation of this new artifact.

## First post-fix live result

Session `scan-hop-f4303bac2380691b` completed with a 300.0766576-second source
span, 2,362 complete dual-RX dwells, **94.4558% duty**, no missing samples or
overflows, and a verified full-IQ reread. All 2,362 source-bound detector records
arrived with zero drops, successful final drain, no publication warning and
successful real-store API checks. PPU verified owned cleanup and restoration.

Every result screened all six temporal slices. None passed the positive-only
gate; all carry `unavailable / incomplete_search`. This reason is also used for
completed bounded searches without a qualifying positive, so it must not be
interpreted as CPU skipping or signal absence. 1,444 results contain fractional
confirmation measurements. Their worker CPU p99 is 88.06 ms; wall p99 is
92.47 ms. These are confirmed-result statistics, not all-callback timing.

The mean retune was 5.47241 ms, scheduler lateness 0.57152 ms and guard 1 ms,
excluding startup. Retune p99 was 11.76984 ms. Compared with the earlier baseline,
duty is **0.9871 percentage points lower**. The provider build changed and runs
were sequential, so this does not isolate GLRT causally. It is nevertheless
**not a passed unchanged-duty gate**, even though it exceeds the 90% target.
The 5 MS/s disabled/enabled pair uses the same post-fix provider artifact.

## Remaining verification

Complete 5 MS/s disabled/enabled and actual adaptive operation within the
remaining RF authority. The old 2.5 MS/s baseline is not an identical-binary
randomized A/B trial. Verify full IQ, source-bound detector inventory, duty and
restored ownership before proceeding.

Receiver input is not independently established as a working Starlink LNB.
Unlabelled RF can qualify streaming mechanics, but cannot prove sensitivity,
absence, or adaptive allocation benefit. Exact release packaging/sealing and
dependency pins, remote-main merges, opt-in deployment, deployed UI and rollback
checks remain open. Raw local evidence is retained separately from credentials.
The [first evidence snapshot](evidence/2026_09_09_radio18_live_startup/index-065.json)
archives 65 allowlisted receipts and recipes with source/archive hashes;
credentials, firmware backups, executables and raw IQ are excluded.
