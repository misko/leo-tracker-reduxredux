# SYSINFO/ULMAP internal handoff in the transmit executable

The function at `3b740` in canonical `catson--bin--tx_lmac` is identified by
its diagnostics as `mac_ctrl_send_sysinfo_ulmap`. Its first send constructs
an internal IPC message, not the previously recovered 11-bit control envelope
or a hardware constellation buffer. The existence of this shared-code function
in the transmit executable does not by itself prove its runtime role.

Fresh instruction execution reaches the first `e3d20` call at `3b82c` with
five pointer/length vectors:

| Vector | Source | Length |
|---|---|---:|
| 0 | Constructed stack header | 20 |
| 1 | Entry x2 + 0x43 | 281 |
| 2 | Entry x3 + 0x10 | 281 |
| 3 | Entry x3 + 0x473 | 321 |
| 4 | Entry x3 + 0x7b9 | 41 |

These total **944 bytes**. The diagnostic identifies the x2/x3 objects as
SYSINFO/ULMAP inputs; the individual vector bodies have not been decoded by
this experiment. Header construction is:

| Header offset | Width | Source |
|---|---:|---|
| 0 | 2 | Constant 2 |
| 2 | 2 | Constant 944 |
| 4 | 4 | Root +0x41610 |
| 8 | 4 | Entry x1 +8 |
| 12 | 4 | Entry w4 |
| 16 | 1 | Low byte of entry w5 |
| 17 | 1 | Entry x2 +0x34 |
| 18 | 1 | Low nibble of byte at entry x3 +2 |
| 19 | 1 | High nibble of that byte |

All multibyte stores are little-endian CPU values. The send's first argument
comes from root's pointer array indexed by root+0xd058; the tested index is 0.
The send diagnostics explicitly name `mpi_ipc_send_iovec`. No assumption that
this header is transmitted over Ku band is justified.

[`tx_sysinfo_ipc.py`](tx_sysinfo_ipc.py) executes `3b740–3b82c` using synthetic
objects and no stubbed calls. Twelve cases exercise nibble separation, byte
truncation, zero/full-width word values and the exact five-vector layout.
The binary is pinned against the corpus manifest; ignored receipt:
`local/tx-sysinfo-ipc.json`. Execution stops before transport. The secondary
target send, caller reachability and downstream serialization are untested.

This narrows the next bridge: find the receiver of internal message type 2,
follow these unpacked structures through control-message serialization and the
transmit scheduler, then determine what modem configuration places those bytes
in RF symbols. The 281-byte vector sizes are **not** evidence that an on-air
SYSINFO header has 2,248 bits. Existing minimal SYSINFO serialization remains a
separate, tested representation.
