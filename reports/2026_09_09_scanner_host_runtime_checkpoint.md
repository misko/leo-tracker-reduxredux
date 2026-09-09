# Scanner host runtime and USB-spare preflight

2026-09-09. No new RF, radio uploads, listeners, firmware/FPGA changes or
production service changes. `.14` remains excluded and was not contacted.

Subsequent explicitly authorized maintenance restored `.18` to released v0.49
and verified 2R2T. See the [restoration checkpoint](2026_09_09_radio18_v49_2r2t_checkpoint.md).
The observations below describe the earlier preflight, not its current firmware.

## Outcome

The operator authorized `.18` for six 300-second captures, but read-only
preflight found incompatible hardware exposure. Exact serial
`1040007c4a94000211000b009186843ef2` was verified both on local USB `3-11` and
physical Ethernet `192.168.1.18`. Its existing firmware is
`v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v7`, boot
`6d49bb26-7d55-4b99-a62f-6c3084443fe5`. Only `voltage0` and `voltage1` are
exposed: two 16-bit storage elements, one complex receiver, not two receivers.
GLRT checks only RX1, but this scanner must still **record both RX**. The normal
pyadi constructor also fails because this RX-only image lacks
`cf-ad9361-dds-core-lpc`. Neither gate was bypassed. The authorized RF matrix
has consumed **zero seconds** and provides no new duty-cycle measurement.

## Host packaging fix

An initial production-loader attempt failed before radio admission because the
development environment lacked its release-local metadata-runtime receipt.
The established ABI-3 installer also pins a source predating GLRT final drain.
PPU commit `06cc399ed45037524d08ef677dd01d977dd83b16` adds an explicit
`--scanner-glrt` option selecting libiio
`a1088b61de3c57762cfed5533e1baf8076a7b726`. Existing defaults, receipt schema,
metadata constructor, exact-path and hash checks are preserved. The additional
runtime is accepted only for ABI 3; its cancel/status/drain signatures are
checked. Arbitrary commits remain rejected.

A local source-repository option supports an unpublished canary build without
building working-tree edits or accepting a caller-selected commit. A fresh
wheel-installed environment was built with frozen dependencies at
`/tmp/leo-scanner-host-runtime.JXTjzr/.venv`. Its installed package entry point
built native and Python pieces from the exact committed source. A new subprocess
with ambient loader/Python overrides removed verifies the runtime successfully:

- Native SHA-256: `a09b77cf0c0101204163abae8c90a6abc170199ee61836c5133dc3194569df3e`.
- Binding SHA-256: `5ed5cb596f24ceeb857b27eefe5303eeb4f1e9ed2c1f2a31a2ca5746d8fa52bb`.
- Backends: local, XML, IP and USB. Radio probes used **IP only**.
- 34 focused installer/verifier tests and 800 capture/lifecycle/stream regressions
  pass, with no skips or failures. Ruff lint and diff whitespace checks pass.

The installed-runtime `.18` probe now passes host verification and fails at the
real radio layout described above. This is a useful negative preflight result,
not a capture pass. Recorded receipts are in
[the evidence directory](evidence/2026_09_09_scanner_host_runtime/).

## Remaining gate

Use a compatible, available, physically USB-connected dual-RX spare over its
verified `192.168.1.*` Ethernet address, under explicit bounded RF authority.
The other USB-visible serial `winbond-db6968136727402c` is at port `3-7`, but its
old `.152` address no longer returns a radio identity; its current address is
awaiting operator confirmation. No firmware change or replacement-radio RF
authorization is inferred.

Production release staging and its native-source inventory pin are unchanged.
This checkpoint does not claim remote merge, production deployment, live duty,
adaptive RF benefit or deployed-browser verification. Those gates remain open.
