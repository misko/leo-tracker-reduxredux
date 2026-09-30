# LDPC telemetry: a constrained hardware-facing lead

The fresh PHY audit identifies the exact register dependency of the exported
field `ldpc_max_iter`. It does not recover an LDPC decoder or configuration
command. This distinction matters before treating a diagnostic field as an
input to RF decoding.

## Evidence

Canonical `catson-bin--phyfw`, SHA256
`52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326`:

| Evidence | Meaning established |
|---|---|
| Relocation at `0x10bda0` points to `0xd0948` | Metadata field name is `ldpc_max_iter` |
| Metadata word at `0x10bda8` is `0x14` | Field offset in exported structure |
| `0x62220`: load pointer from object `+0xcd8` | Source register-bank pointer |
| `0x62224`: load 32-bit word at bank `+0xd04` | Register source |
| `0x62228`: shift right 8; `0x6222c`: store byte at output `+0x14` | Exported value is `(word >> 8) & 255` |

`ldpc_iteration_telemetry.py` verifies the ELF metadata using segment-aware
address translation, then executes these four instructions for 35 register
patterns: zero, all ones, `0x12345678` and all single-bit values. Read hooks
verify one four-byte register read. The register remains unchanged, and only
the intended output byte changes. This checks the bit dependency, not the
physical interpretation of the byte.

## What remains unknown

The label suggests an LDPC iteration-related quantity. The audited code does
not distinguish a configured limit from a measured maximum or other hardware
status. No units, reset interval, writer or live value have been established.
It does not give the parity-check matrix, block length, code rate, scrambling,
interleaving or placement of SYSINFO in an RF frame.

A direct disassembly search for immediate offset `0xd04` also finds halfword
accesses relative to software objects. Equal numeric offsets do not establish
the same register bank. No direct register writer was identified by that
bounded search; computed-address and indirect accesses remain possible.

Earlier work already identified LDPC codeword/correction counters and MODCOD
tables. Those results were not counted as new or rerun here. This new field
mapping supplies a narrower target: trace the origin of object `+0xcd8` and
writers into its bank, keeping configuration writes separate from telemetry.
It does not yet justify a new blind DS7–DS10 decoding scan.

## Reproduction

Run `ldpc_iteration_telemetry.py` with the existing pyelftools/Unicorn environment.
Receipt: `local/ldpc-iteration-telemetry.json`. Component regression:
`test_ldpc_iteration_telemetry.py`. Extracted data remain ignored by Git.

## Constructor-derived bank address

The constructor at `0x5db70` preserves argument X2 in X20, then its pointer
setup at `0x5dba8`–`0x5dc00` installs these offsets from that supplied base:

| Object member | Supplied base plus |
|---|---:|
| `+0xc98` | `0x0000` |
| `+0xcb0` | `0x4000` |
| `+0xcd0` | `0x5000` |
| `+0xcd8` | `0x8000` |

In particular `0x5dbcc` computes base + `0x8000`; `0x5dbf8` stores that pointer
through the object `+0xcd8` address computed at `0x5dbdc`. Composing this setup
with the telemetry reader puts `ldpc_max_iter` at **supplied base + `0x8d04`,
bits 8–15**. The extended assay executes both instruction windows for the same
35 register patterns at two different bases: 70 cases verify address relocation
and identical output semantics. The receipt now contains these 70 cases,
superseding the initial single-bank 35-case receipt.

The direct call at `0x30908` loads this base into X2 from `[X21+8]` at `0x308f4`.
This connects the constructor input to a caller mapping structure, but does
not establish its runtime physical address. The constructor's own allocation
and preceding base-class initialization are not executed in this assay.

Two false aliases were excluded by inspecting their bases: the halfword zero
store at `0x5dc44` is to **object** `+0xd04`, while the load at `0x75af4` uses
`0x10f000 + 0xcd8` as a GOT lookup. Neither is a demonstrated write to the
telemetry register. A setter for register bits 8–15 remains unidentified;
the label alone still cannot distinguish a configured limit from measured
status. No new RF decoding hypothesis follows until that distinction or an
independent coding constraint is established.
