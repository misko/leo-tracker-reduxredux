# Capture issue catalog: 20-hour production window

## Scope and headline

This audit freezes the interval **2026-09-17 06:46 through 2026-09-18
02:46 UTC**. It covers the production adaptive schedule on radio serial
`104000bac4950008230026001b440a003a`, RX0 only, with one 300-second slot every
10 minutes and a repeating 20/10/15 MS/s rate sequence.

The scheduler offered 120 slots. Ninety-two reached a terminal firmware archive,
82 were accepted by the scanner importer, and 38 did not become usable scanner
sessions. The principal loss is firmware `ETIME` at 20 MS/s. Disk throughput is
not the observed cause: captures were written to the NVMe spool first, failed
sessions ended in the firmware qualification protocol before a terminal archive
existed, and successful 20 MS/s sessions wrote about 20.5 GB each through the
same path.

| Rate | Scheduled | Terminal archive | Rejected for skipped visits | Imported | Import yield |
|---:|---:|---:|---:|---:|---:|
| 10 MS/s | 40 | 38 (95%) | 0 | 38 | 95% |
| 15 MS/s | 40 | 36 (90%) | 2 | 34 | 85% |
| 20 MS/s | 40 | 18 (45%) | 8 | 10 | 25% |
| **All** | **120** | **92 (76.7%)** | **10** | **82** | **68.3%** |

The reproducible, slot-level source for these totals is
[`slot_ledger.csv`](figures/2026_09_18_capture_issue_catalog_20h/slot_ledger.csv).
It identifies every scheduled UTC time, rate, session ID, terminal status,
skipped-visit count, and import outcome. Counts below refer to unique slots or
archives unless explicitly described as log occurrences.

## Issue ownership and follow-up catalog

| Issue | Evidence and effect in this window | Likely boundary | Primary follow-up repository | Secondary repository | Recommended follow-up |
|---|---|---|---|---|---|
| Firmware session expires with `ETIME` (`error=-62`, reason 3) | **28 unique slots** produced no terminal archive: 2/40 at 10 MS/s, 4/40 at 15 MS/s, and 22/40 at 20 MS/s. The terminal reports consistently end with two or more cancelled visits; failures range from 6/8 visits delivered to 1,497/1,499, so this is not simply a startup failure. | Firmware adaptive-session deadline, queue ageing, and terminal completion semantics. | [`misko/plutosdr-fw`](https://github.com/misko/plutosdr-fw) | [`misko/pluto-plus-utils`](https://github.com/misko/pluto-plus-utils) for protocol diagnostics and retry policy; scanner for scheduling/backoff | Add a firmware test that runs the production 120 ms dwell plan for 300 s at each rate and requires a successful terminal receipt. Record which deadline fired and queue/DMA/transport watermarks. Host should retry only bounded early failures and preserve the terminal diagnostic. |
| Firmware completes but reports skipped visits | **10 terminal archives** were sparse: 2 at 15 MS/s and 8 at 20 MS/s. Missing visits ranged from 1 to 13. The IQ and receipt remain on NVMe, but the importer rejects the session. | Visit production/transport loss is firmware-side; consuming an explicitly sparse archive is a scanner capability. | [`misko/plutosdr-fw`](https://github.com/misko/plutosdr-fw) for preventing or precisely classifying skips | [`misko/leo-tracker-reduxredux`](https://github.com/misko/leo-tracker-reduxredux) for sparse import | Firmware tests should assert `delivered + skipped + invalid + cancelled == planned` and expose per-visit reasons. Scanner should import the delivered visits with explicit gaps, retain the terminal integrity status, and prevent interpolation across gaps. |
| Importer describes every sparse archive as “sparse 10 MS/s import unsupported” | The message is emitted for the 15 and 20 MS/s archives too. It hides the actual rate and makes operations triage misleading. It does not cause acquisition loss, but it turns ten recoverable archives into invisible scanner sessions. | Scanner import validation and operator diagnostics. | [`misko/leo-tracker-reduxredux`](https://github.com/misko/leo-tracker-reduxredux) | None | Make the error rate-neutral immediately; then add red/green fixtures for one skipped visit at 10, 15, and 20 MS/s and implement truthful sparse import. |
| Alternate iiOD readiness probe fails during capture setup | The acquisition journal contains **162 raised lifecycle errors** (324 matching traceback lines). The scheduler retries and many slots eventually capture, but setup churn consumes the beginning of slots and co-occurs with late starts. | Host lifecycle/readiness around the userspace iiOD launched on the PPU. | [`misko/pluto-plus-utils`](https://github.com/misko/pluto-plus-utils) | [`misko/libiio`](https://github.com/misko/libiio) and firmware packaging in `plutosdr-fw` | Replace the shallow port probe with an attested context/device/buffer readiness handshake; include child exit status and daemon log tail; make startup idempotent. Test repeated start/stop and reboot recovery over PPU Ethernet. |
| Metadata buffer creation returns `EOPNOTSUPP` (`Errno 95`) | **25 exception chains** (50 direct `OSError` lines plus 25 wrapped scanner errors) occurred. Retries/fallback allowed later capture, so these are not 25 lost slots. The symptom persisted throughout the window. | Capability negotiation between libiio client, alternate iiOD, kernel device, and host capture adapter. | [`misko/libiio`](https://github.com/misko/libiio) | `pluto-plus-utils`, then `leo-tracker-reduxredux` for fallback policy | Add a negotiated metadata-capability query and a red/green test proving unsupported metadata is rejected before buffer construction. The host should select the standard buffer path once per attested daemon instance instead of rediscovering failure within scheduled work. |
| Durable operation key differs from durable slot | **80 logged scheduler failures** occurred, generally as retry noise rather than terminal slot loss. This is a host state/idempotency defect and can obscure the firmware failure that follows. | Scanner durable scheduling contract. | [`misko/leo-tracker-reduxredux`](https://github.com/misko/leo-tracker-reduxredux) | None | Derive both values from one persisted slot record, make repeated invocation idempotent, and add a concurrency test for timer overlap/restart recovery. Emit one outcome per slot rather than one failure per retry. |
| Captures lack qualified absolute UTC timing | All **92 terminal archives** have only a host begin bracket, **211.9–256.3 ms wide** (median 214.5 ms). Relative sample-counter timing is usable, but the scanner correctly refuses strong TLE identity claims from this timing authority. | The firmware protocol lacks a sufficiently tight device-counter to UTC observation; scanner qualification is correctly conservative. | [`misko/plutosdr-fw`](https://github.com/misko/plutosdr-fw) | `pluto-plus-utils` for transport and `leo-tracker-reduxredux` for consuming the contract | Return a device sample counter latched against a PTP/PPS/UTC source, or a tightly bracketed host transaction with measured asymmetric delay. Define and test the maximum uncertainty required by tracking before marking it qualified. |
| Transfer/import worker has large periodic resource spikes | Normal no-op/reconcile runs use about 277 MB and 20–25 s. New large archives triggered observed peaks of **7.8–16 GB** and **2:13–3:55 wall time**. Publishing can lag, though no capture loss maps to these spikes because acquisition writes the separate NVMe spool. | Scanner storage/import implementation. | [`misko/leo-tracker-reduxredux`](https://github.com/misko/leo-tracker-reduxredux) | None | Stream copy/hash/import rather than materializing visit data, checkpoint processed session IDs, avoid rescanning/re-reporting the full historical set each minute, and publish queue age/bytes as metrics. Add a bounded-memory 20 MS/s archive import test. |

## What did not fail

- The selected radio and receiver are consistent in every inspected terminal
  manifest: serial `104000bac4950008230026001b440a003a`, `rx_mask=1`, physical
  receiver 0.
- The NVMe-first architecture is functioning. Terminal archives exist for all
  three rates, including complete 20 MS/s captures, and the background worker
  copies/imports them independently of acquisition.
- The two historical “not centred on a canonical pilot (960000000 Hz)” archives
  in the current unsupported list completed before this 20-hour window. They are
  therefore excluded from the incident counts here.
- Missing Doppler/TLE products caused by absent qualified UTC or by no eligible
  trajectory are downstream truthfulness decisions, not additional IQ-capture
  failures.

## Recommended order

1. Fix and instrument firmware `ETIME`, using the production 300-second plan as
   the acceptance test. It accounts for all 28 slots with no archive and is the
   dominant 20 MS/s failure.
2. Teach the scanner to import sparse archives without inventing samples. This
   immediately recovers ten existing sessions for partial analysis while the
   firmware skip source is investigated.
3. Stabilize and attest the alternate iiOD lifecycle, then negotiate metadata
   capability once. These retries currently add noise and make causal diagnosis
   harder.
4. Add a qualified device-counter/UTC contract. Without it, better sample rate
   does not turn Doppler resemblance into a defensible catalogue association.
5. Bound transfer memory and make reconciliation incremental so web publication
   remains prompt as 20 MS/s volume grows.

The acceptance dashboard should report four distinct quantities per rate:
scheduled slots, successful firmware terminals, importer-accepted sessions, and
analysis-qualified sessions. Collapsing these into one “capture success” number
would hide both firmware loss and recoverable sparse data.
