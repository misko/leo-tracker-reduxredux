# Hardware canary — 2026-08-19

Status: bounded canary passed; long soak and repeated-trial gates remain pending.

## Environment

- Host: `gauss`
- Radio A: `ip:192.168.1.20`, serial
  `1040005e0b100007100010000bf33a5d4d`
- Radio B: `ip:192.168.1.21`, serial
  `10400056f695001322002d0010ad1719f2`
- Firmware observed on both:
  `v0.38-plutoplus-spf-libiio-metadata-v5`
- Adapter provenance: `pluto-plus-utils` revision
  `d5cd29301c5b36b3d65f8433af1508f2650eadea`
- Profile: `hardware-canary-2p5m-1s`, 2.5 MS/s, dual RX, one second,
  CI16, manual 30 dB gain, Zstandard level 3.

## Single-radio result

- Session: `canary-single-20260819-001`
- State: committed
- Samples: 2,500,000 on both receiver paths
- Uncompressed IQ: 20,000,000 bytes
- Compressed IQ: 6,466,566 bytes
- Refills: 10
- Gaps/overflows: 0/0
- Manifest SHA-256:
  `sha256:b30720ddc6ed16e4ff2dbd38e7ba17825d3bb0948662094d3b1192385086ab16`
- Full bundle digest verification: passed

## Dual-radio result

- Session: `canary-dual-20260819-001`
- State: committed
- Streams: 2 complete radios, 2 RX paths each
- Samples: 2,500,000 per radio stream
- Uncompressed IQ: 40,000,000 bytes
- Compressed IQ: 19,447,954 bytes
- Refills: 10 per stream
- Gaps/overflows: 0/0 on both streams
- Estimated start skew: 721,484 ns
- Start-skew uncertainty: 93,731,220 ns
- Estimated overlap: 875,862,791 ns
- Guaranteed overlap: 799,546,433 ns
- Overlap fraction: 0.9991769371
- Phase-coherence claim: false
- Manifest SHA-256:
  `sha256:bbec2718e93aa255ecae8eae337974016eb3667145d651467422b69c7afe721e`
- Full bundle digest verification: passed

## Remaining qualification

- Repeat 100 bounded synchronized trials and measure the pass distribution.
- Exercise a deliberate peer failure while preserving the surviving stream.
- Complete the 24-hour scheduled acquisition soak.
- Verify capture health under an induced processing backlog.

