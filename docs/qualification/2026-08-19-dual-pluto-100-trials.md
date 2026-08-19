# Dual-Pluto repeated acquisition qualification — 2026-08-19

This report records a bounded hardware qualification on the dedicated host. It
is evidence for the repeated-readiness and best-effort synchronization gates;
it is not a substitute for the required 24-hour soak.

## Configuration

- profile: `hardware-canary-2p5m-1s`
- radios: `radio_pluto_5d4d`, `radio_pluto_19f2`
- receivers: two per radio
- sample rate: 2.5 MS/s per receiver
- trials: 100 one-second captures
- acceptance policy: at least 95% successful trials, estimated overlap at least
  99% on at least 95% of successful trials, all digests valid, and no false
  complete or phase-coherent claims
- immutable receipt:
  `/srv/bulk/leo/qualification/acquisition/dual-pluto-100x-20260819-001.json`

The command used the production Pluto adapter and verified each published
recording bundle after its manifest-last commit. Qualification recordings were
preserved beneath `/srv/bulk/leo/recordings`; no QNAP path was written.

## Result

The qualification passed.

| Measure | Result |
| --- | ---: |
| Successful / committed | 100 / 100 |
| Degraded / failed | 0 / 0 |
| Trials meeting 99% estimated overlap | 100 / 100 |
| Corrected mean estimated overlap fraction | 0.99949934 |
| Corrected minimum estimated overlap fraction | 0.998089948 |
| Mean estimated start skew | 500,660 ns |
| Maximum estimated start skew | 1,910,052 ns |
| Mean timing uncertainty | 90,751,540.66 ns |
| Maximum timing uncertainty | 107,549,785 ns |
| Guaranteed overlap | 0 ns (not observable without device counters) |
| Gaps / overflows | 0 / 0 |
| Valid / invalid bundle digests | 100 / 0 |
| False complete / false coherent claims | 0 / 0 |
| Uncompressed / compressed bytes | 4,000,000,000 / 1,967,145,322 |
| Compression ratio | 2.0334:1 |

Post-run review found that the original receipt calculated overlap from host
read completion spans, which can exceed the sample-clock duration when reads or
compression are delayed. That receipt and the immutable capture manifests were
not rewritten. The corrected estimator uses half-open sample-clock intervals,
caps overlap by captured samples/sample rate, and treats device-counter-free
Pluto streams as degraded with `sample_loss_observable=false` and zero
guaranteed overlap. Re-evaluation under those rules still leaves all 100 trials
above the 99% estimated-overlap threshold, with the corrected aggregate values
shown above. This supersedes the receipt's overly strong guaranteed-overlap
figures while retaining them as auditable failed evidence. The system does not
claim hardware triggering or cross-radio phase coherence.

## Writer capacity check

The production 128 MiB Zstd shard geometry sustained 117.699 MB/s over a
10-second generated, incompressible CI16 run, exceeding the 60 MB/s gate and
the 40 MB/s aggregate raw rate of two dual-RX radios at 2.5 MS/s. Its bundle
digest verified successfully. Receipt:
`/srv/bulk/leo/qualification/writer/writer-20260819-10s-128m-001.json`.

A deliberate 4 MiB-shard comparison sustained only 39.9998 MB/s and failed the
60 MB/s gate. That receipt is retained at
`/srv/bulk/leo/qualification/writer/writer-20260819-10s-001.json`. This result
demonstrates why production and qualification use 128 MiB shards; it is not
discarded or relabeled as a pass.

The underlying RAID was rebuilding at approximately 50 MB/s during these
measurements. Treat both writer rates as conservative observations of a
temporarily degraded storage state, not final capacity tuning inputs. Repeat
the sustained benchmark after the rebuild completes before fixing worker or
admission limits from storage throughput.

## Remaining qualification

- a full 60-second real-dwell detector run;
- capture while processing backlog is deliberately induced;
- service restart/reconciliation and storage-pressure campaigns;
- the required 24-hour scheduled acquisition soak with RSS and continuity
  monitoring.
