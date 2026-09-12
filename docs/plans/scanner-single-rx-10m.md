# Single-receiver 10 MS/s long scan

The requested profile records one Pluto receiver at 10 MS/s for a 300-second
device-time scan. Choose RX0 or RX1 with equal probability once before opening
the radio; persist the choice in the queued intent. Replaying or retrying that
intent must never redraw the receiver. Physical RX1 remains labeled RX1 even
though it occupies column zero of the single-channel payload.

## Evidence and scope

The 2026-09-12 bounded fixed-tuning transport measurements used the same Pluto,
ordinary metadata path and 8 x 131,072 sample buffers. At 10 MS/s, RX0-only
delivered 100% of a 30-second FPGA window, whereas dual RX delivered 61.56%.
These measurements justify a single-RX profile; they do not qualify hopping,
on-radio classification, a 300-second duration, or full analysis.

Retain the eight pilot-edge targets and 120 ms valid visits, with the existing
20-minute slot cadence. Receiver selection uses one domain-separated SHA-256
bit of the radio serial and durable operation identity: it is pseudorandom
between scans and stable through retries. The explicit new profile uses fixed
target order and host analysis; the older on-radio adaptive classifier is not
qualified for 10 MS/s. One receiver produces 40 MB/s raw CI16, at most approximately
12 GB of valid IQ in 300 seconds before compression.

## Implementation sequence

1. Add a new versioned profile and queued intent. Bind profile ID, exact rate,
   physical receiver, duration, tuning plan, and randomness provenance into the
   intent digest before radio admission. Preserve every old published contract
   and every old recording decoder. Test both receiver outcomes and retry
   stability, including concurrent attempts to resolve one queued operation.
2. Extend the capture capability through the narrow radio port. The existing
   persistent-hop provider requires dual RX, and the adaptive classifier pins
   RX1 and 2.5/5 MS/s. A successful ordinary RX0 transport test must not bypass
   those checks. Add an explicitly advertised capability and compatible new
   contracts where needed; qualify receiver masks, CI16 byte stride, FPGA
   counters, setting restoration, and bounded backpressure before deployment.
3. Persist single-channel IQ with the actual receiver identity and exact
   10,000,000 Hz clock. Preserve separate stored-payload and FPGA-time
   coordinates, including every retune guard and missing interval. Reuse the
   existing local-filesystem writer and analysis ports.
4. Extend the full 300-second analysis and presentation path. Verify native
   10-MS/s pilot templates (44 samples per 4.4 us symbol), 20-ms probes
   (200,000 samples), fractional 750-Hz frame epochs, CFO in Hz, actual LO
   offsets, timestamp conversion, and RX1-to-column-zero mapping. Update
   hardcoded two-receiver coverage checks. Do not synthesize an absent second
   receiver or label data at another sample rate to satisfy a validator.
   Preserve the current production analysis density: one 20-ms probe per
   120-ms visit. All 120 ms of valid IQ remain stored for denser reanalysis.
5. Run component-owned tests, then a bounded end-to-end canary through the
   real writer and analysis path. Only promote after the manifest can be
   reopened, all counter/byte accounting closes, both receiver choices are
   covered by adapter tests, and completed analysis reports correct rates,
   receiver identity, coverage, and numerical results.
6. Stage an immutable release, retain the prior release/settings for rollback,
   switch the scanner profile through the supported deployment/control path,
   and inspect one bounded production run. Do not run an extended RF campaign.

## Scientific acceptance

- Synthetic native-rate pilots recover known timing and CFO at 10 MS/s.
- RX0-only and RX1-only reader fixtures produce the same numerical results
  when their IQ is identical, while preserving distinct physical RX labels.
- A test with retune gaps preserves actual elapsed time and Doppler slope;
  concatenating valid samples must not compress the timeline.
- New serialized records round-trip through storage and analysis; historical
  dual-RX 2.5/5-MS/s fixtures remain unchanged and continue to load.
- Report measured valid duty separately from source continuity. Hopping cannot
  truthfully claim 100% valid single-frequency coverage.

## Operational acceptance

Only one process owns the radio; the receiver is held constant for the entire
scan. A canary must account for all received/missing/transition-invalid samples,
meet the existing 90% valid-duty target if hopping, and complete storage and
analysis without fabricated results or silent rate fallback. Bound each RF
collection to at most 30 minutes; use existing recordings and synthetic inputs
for repeated analysis work. A failed gate leaves the existing production
profile selected and records the concrete blocker.
