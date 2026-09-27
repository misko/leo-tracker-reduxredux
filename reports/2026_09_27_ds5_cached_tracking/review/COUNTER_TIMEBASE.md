# DS5 development source-counter timebase audit

## Finding

The frozen development source counters use one count per simultaneous dual-RX
sample instant. There is no factor-of-two counter-scale defect in either
development block. For causal replay within a session, elapsed sample time is

```text
(later_source_counter - earlier_source_counter) / rate_hz
```

Both receiver lanes share that source coordinate. Do not multiply or divide the
counter delta by the receiver count.

The v0.59 defect fix addressed the interval used to inject counter words into a
dual-RX packed stream. Pre-fix kernels programmed a per-channel sample count
where the FPGA expected a count of packed 64-bit words, allowing counter words
to leak into IQ payloads. The retained root-cause receipt does not describe the
HOPT source coordinate as advancing at the wrong rate.

## Metadata evidence

This review read only the two development recording manifests and frozen public
receipts. It did not read holdout IQ or detector outcomes.

| Development session | Rate | Source span | Span / rate | Saved visit span | Consecutive saved-start deltas |
|---|---:|---:|---:|---:|---:|
| `scan-fw-1a0e881391ba1d2f` | 2,500,000 Hz | 750,000,000 | 300.000 s | 300,000 = 120 ms | 120.0096–140.7468 ms |
| `scan-fw-3ec1c634e1f48f77` | 5,000,000 Hz | 1,500,000,000 | 300.000 s | 600,000 = 120 ms | 120.0174–140.8060 ms |

For all 128 development cases:

- `source_start_counter` equals an event's `valid_start_counter`;
- `source_end_counter_exclusive` equals that event's
  `valid_end_counter_exclusive`;
- the end-minus-start span is exactly the declared 120 ms dwell at the session
  rate;
- starts increase strictly, including the counter time consumed by retunes;
- both manifests declare `sample_receiver_iq`, metadata ABI 3, and radio serial
  `1040005e0b100007100010000bf33a5d4d`.

The manifest file hashes are independently pinned by `dataset/cases.json`:

- 2.5 MS/s: `453a35dc3acb7dc51f25f6e114570b7eaffe9803f168e54b6088b10b5c250292`
- 5 MS/s: `fcf4ed15398ad2057a69d576e08760fd3ce685626069d61ac69438ecd5284d04`

## Firmware provenance

The successful production deployment receipt
`f9bf1a40-cd53-4b6b-81af-0d88e85063f9` records the same radio changing from
`v0.58-plutoplus-spf-adaptive-multirate-agc` to
`v0.59-plutoplus-spf-dual-rx-counter-fix`. Its file was finalized at
2026-09-26 04:53:12 UTC and its SHA-256 is
`61182779c6419f172d5e5eefba3c2cb84064f23450684dc8707ff8ea67f7ccc7`.
The 5 MS/s development session began between 09:30:02.952 and 09:30:03.320
UTC; the 2.5 MS/s session began between 11:50:02.762 and 11:50:03.132 UTC.
This strongly places both captures after the v0.59 deployment.

The recording manifest contract does not persist the firmware name or FIT hash.
Consequently, the manifests alone cannot cryptographically prove that no
intervening reboot or rollback occurred. The deployment receipt, matching
serial, capture times, current attestation, and direct counter-scale invariants
support v0.59 provenance, but that provenance is an inference across receipts.

## Effect on causal claims

Existing development claims about causal ordering, cache age in sample time,
and source-counter epoch prediction do not need correction. They should retain
three qualifications:

1. The coordinate establishes elapsed sample time within each session; it is
   not an exact UTC clock beyond the manifest's host bracket.
2. State must reset at every session boundary or counter/timebase reset. Ordinary
   retune gaps and missed visits retain a meaningful counter delta; the frozen
   cache handles those through its age limit rather than resetting on every gap.
3. Firmware provenance is receipt-linked rather than embedded in each recording
   manifest. A future live equivalence claim should persist firmware/FIT identity
   in the recording receipt.

Even under the unsupported hypothesis that either session had run pre-v0.59,
the measured source-counter scale would remain correct. The separate concern
would be possible counter-marker contamination of IQ and detector results, not
the causal time conversion used by the cache.
