# Local PLUTO+ source adapter

This component is the C10 local PLUTO+ boundary. It uses the firmware scan
owner ioctls and an ordinary `local:` libiio context. It never creates a
network or USB context and never transfers IQ through iiOD.

`local_radio_prepare.h` is the bufferless preparation boundary. The application
first reserves the exclusive counter-device session without activating the
firmware owner. Under that reservation it snapshots RX state and kernel-buffer
count, programs and attests source/capture rate, factor-one FPGA path,
bandwidth, paired-RX layout, manual gain, and the receive-only TX guard. It
compiles every volatile Fast Lock slot through store/save/recall, reloads the
immutable 16-byte image after ordinary tuning and again after recall may change
its ALC byte, and forces an attested distinct ordinary transition to exit Fast
Lock. The distinct transition is also used when a one-profile setup repeats the
clock framework's cached LO value. Profile 0 is valid; emitted CRC32 values
cover the immutable bytes. Preparation-failure receipts retain the original,
configured, and cleanup-restoration observations.

Source-open then activates the firmware owner on the same descriptor. At the
end, source-close returns the descriptor, the application deactivates the
firmware owner, restores RX state and buffers while the exclusive reservation
remains held, and finally closes it. AGC gain is observational; manual gain is
restored exactly. Restoration handles remain retryable after transient errors.
TX stays muted as an intentional receive-only safety condition.

This makes volatile profiles self-contained after a firmware reboot. External
preconditions are the qualified firmware/local-libiio ABI and no unrelated
local or network IIO writer changing radio attributes during preparation or
restoration. The reservation excludes other counter/tandem sessions; only the
active firmware owner blocks ordinary IIO writes, and it cannot be active while
profiles are being programmed.

The installed 0.59 libiio exports local buffer refill but does not export the
newer block-lease calls present in the reference source. The production
provider therefore owns one ordinary local buffer and exposes one logical
lease. A release keeps that buffer's bytes valid; the following refill returns
the DMA block to the kernel and replaces them. The public adapter forbids a
second outstanding lease, retune, or snapshot while bytes are borrowed.
Every provider also supplies a thread-safe cooperative cancel operation. The
scanner deadline thread uses it to wake a blocked acquire before close and
restore. The local-IIO provider sets the context timeout explicitly to 1000 ms
and implements cancellation with `iio_buffer_cancel`; no signal handler enters
libiio.

The first eight raw DMA bytes carry the little-endian 64-bit receive counter.
The adapter subtracts the documented two-sample packing offset, rejects
regression and malformed block sizes, and reports exact gaps. `prime` discards
one completed pre-retune block and binds that full-width counter to a coherent
firmware snapshot. Only then may a caller recall a profile. Recall receipts
carry `previous_valid_end` and `valid_start`; `leo_local_block_clip` intersects
a leased block with those boundaries. There is deliberately no UTC field.

The counter device is opened read/write with a nonblocking exclusive file lock.
The kernel acquire ioctl remains the authoritative cross-process owner. Close
releases any borrowed block, asks the firmware owner to restore the prior
frequency, closes local capture, and returns the restoration counters.

Build host, sanitizer, and deployable ARM artifacts with:

```sh
native/adaptive/device/local/build.sh host /tmp/leo-local-host
native/adaptive/device/local/build.sh sanitize /tmp/leo-local-sanitize
native/adaptive/device/local/build.sh arm /tmp/leo-local-arm
```

The ARM build emits `libleolocal.a`, `libleolocal.so`, `test-local-source`,
`test-local-radio-prepare`, `leo-local-radio-prepare`, and `leo-local-capture`.
The preparation diagnostic requires explicit `--prepare-only`, creates no IQ
buffer, does not activate the firmware scan owner, and always restores before
releasing its reservation:

```sh
leo-local-radio-prepare --prepare-only --duration-ms 30000 \
  --target 0 2400000000 [--target PROFILE FREQUENCY_HZ ...]
```

The capture diagnostic is bounded to 100 120-ms blocks and emits
only counter/validity receipts:

```sh
leo-local-capture FREQUENCY_HZ BLOCKS_1_TO_100 [PROFILE_CRC32] [RECEIVERS_1_OR_2]
```

Creating the executable does not authorize live capture. Its fake-provider
tests cover ownership, counter rollover, gaps, transition clipping, lease
lifetime, malformed data, disconnection, and restoration without device access.
Preparation fakes cover reservation/activation/deactivation phases, profile 0,
ALC mutation, immutable reload, CRCs, gain attestation, and failure restoration.
