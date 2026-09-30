# Receive hardware mappings from unpacked device trees

The new extraction supplies independent device-tree evidence for the addresses
observed in RX MAC and PHY code. `device_tree_receive.py` parses raw FDT
properties, verifies each source against the extraction manifest, and records
register cells, parent ranges, status and compatible strings. It inventories
47 unique small device trees: **26 from the current unpacked Catson SXV** and
21 from the separately existing `linux.fit`. The latter has different bytes
and is kept under separate provenance; it is not assumed to be the same build.

The current package has two groups for the seven inspected mappings:

| Region | Group A: 11 trees | Group B: 15 trees | Declared size |
|---|---|---|---|
| modem_rx | `0x0c000000` | same | `0x20000` |
| modem_rx_ipp | `0x0c030000` | same | `0x3000` |
| syscfg_adc | `0x0c400000` | same | `0x100000` |
| modem_adc | `0x0c500000` | same | `0x1000` |
| l2_ut_rx_push | `0x0c204000` | `0x0c228000` | `0x2000` |
| l2_ut_rx_common | `0x0c206000` | `0x0c22a000` | `0x1000` |
| l2_ut_rx_pull | `0x0c207000` | `0x0c22b000` | `0x1000` |

Group A includes utdev3, mmut2, rev1 variants, early rev2 variants and
transceiver rev2p0/rev2p5 without the cut4 suffix. Group B includes utdev4,
mmut4, rev2_proto4, rev3_proto1, rev4, mini1, hp1 and the two cut4 transceiver
trees. The receipt enumerates every exact source filename and hash.

For utdev3, the parent uses `sx,simple-mmap`, is marked `okay`, and declares
identity ranges for these register banks. Its RX push region spans two 4-KiB
banks, matching the canonical RX firmware's previously traced mappings at
`0x0c204000` and `0x0c205000`. The ADC declarations likewise corroborate the
PHY mappings. These are declarations and code agreement, not observed hardware
execution or proof of the board variant used by any recording.

A check initially assuming all current trees shared the canonical FIFO base
failed. Inspecting the failures revealed the second mapping above. The test
now pins only the named utdev3 reference while retaining all variant results.
This prevents a wrong universal mapping from entering the receive trace.

`dtc` can display the RX push `reg` bytes as strings because some bytes happen
to be printable. The script interprets register properties as big-endian
32-bit cells; a component test covers that exact ambiguity.

## Consequence for tracing identity

This independently locates the hardware-facing input to `rx_lmac` and identifies
a variant boundary to respect when auditing the packet producer. It does not
expose FFT/FEC implementation, on-air SYSINFO positioning or a satellite-ID
mapping. Next work can compare the producer-facing registers and initialization
in the matching `_v4` executable against the canonical trace, using these
addresses as an independent constraint rather than conducting a blind scan.

Reproduce: `python3 device_tree_receive.py`. Receipt:
`local/device-tree-receive.json`. Tests: `test_device_tree_receive.py`.

## Executed V4 cross-check

The address constraint locates V4 initialization at `0xbe324–0xbe390`.
It maps the same `l2_ut_rx_push` sysfs path with offsets 0 and `0x1000`,
length `0x1000` each. Fallback branches at `0xbe6fc` and `0xbe748` use
`/dev/mem` offsets `0x0c228000` and `0x0c229000`. The extended
`register_mapping.py --v4` executes this window for all four combinations
of primary-map success/failure, checking both installed bank pointers.
Mapping and logging calls are stubbed; no device is opened. The canonical
four cases also still pass. Binary hashes are pinned to the existing atlas.

The nearby V4 register reader at `0xbdbd0` follows object `+8`, private `+8`,
and reads a 32-bit word from bank `+0x34 + 4*(selector & 0xff)`. A separate
probe executes the complete reader for selectors 0/1 and 35 values each,
including every one-hot bit, verifying exactly one 4-byte bank read. These
**70 cases** agree with the canonical reader's relative offsets `+0x34/+0x38`.
The V4 reader's full virtual dispatch and queue selection are not executed
by this probe; matching offsets alone do not prove the whole receive chain.

This independently reconciles the initialization with device-tree group B.
It supplies no additional message fields or demodulation algorithm. Future
cross-variant work can keep physical bank movement separate from descriptor
format changes instead of assuming both must change together.

Reproduce: `python register_mapping.py --v4` and `python v4_fifo_word.py` in
the existing Unicorn/Capstone/pyelftools environment. Receipts are
`local/register-mapping-v4.json` and `local/v4-fifo-word.json`. Three component
tests cover the canonical mapping, V4 mapping and V4 word reader.
