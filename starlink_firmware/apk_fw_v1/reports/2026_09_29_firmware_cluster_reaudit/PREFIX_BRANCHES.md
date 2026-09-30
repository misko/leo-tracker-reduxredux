# Prefix branches: instruction execution and cluster interpretation limits

Fresh ELF-mapped disassembly and bounded Unicorn execution confirm three software
prefix layouts. This extends the initial static audit to the signaling branch
and to every writer width/offset combination. It is not an RF decoder.

## Initialization and actual serialization

At `tx_lmac` 0xc1340, a helper initializes the writer. Its return is copied into
w5 at 0xc1344; the following nonzero branch handles failure. Therefore w5=0 on
the successful normal path into packing. This is not an independent message
flag supplied by a caller. At 0xc134c–0xc1350 the routine stores 0x0f03 on the
stack: the indexed count mask is 3 for the short form and 15 for the long form.
The emulation uses this actual initialization, not an assumed all-ones mask.

The mode byte comes from caller w1, masked at 0xc1228. Mode 1 takes the branch
at 0xc1364. Its prefix is eight bits and equals `2 | (flag << 2)` for the tested
binary flag input: 0x02 or 0x06. The sequence-related two-bit value, supplied
length and MCS-count inputs do not affect this prefix. The mode-1 branch explicitly
zeroes w4 and w28 and bypasses their normal serialization.

On the tested non-signaling mode-0 path, with LSB-first software bit numbering:

| Bits | Short form, 8 bits | Long form, 16 bits |
|---|---|---|
| 0–1 | Zero on this successful path | Zero on this successful path |
| 2 | Masked flag | Masked flag |
| 3 | Zero | One |
| 4–5 | Caller state, low two bits | Caller state, low two bits |
| 6–7 | Count, low two bits | Length, low two bits |
| 8–11 | Not in prefix | Length, remaining four bits |
| 12–15 | Not in prefix | Count, four bits |

The field names “length” and “count” follow previously traced software context;
this execution independently verifies packing, not their physical units or
placement on air. Other mode inputs and complete caller reachability remain
outside this bounded experiment.

The actual writer at 0xe1430 masks its input to the requested width, appends it
at the current low-bit cache offset and flushes a little-endian 32-bit word when
needed. All 1,024 combinations of widths 1–32 and starting offsets 0–31 match
an independent integer append model. This includes the 32-bit mask special case
and crossing a word boundary. All 96 combinations in the frozen prefix grid
(two modes, two forms, four state values, two flags and three length/count pairs)
match the branch formulas. This demonstrates software-cache order, not RF order.

## Consequences for the association ledger

| Candidate interpretation | Ranking after audit | Falsifiable requirement |
|---|---|---|
| A two-/four-way tree split is the sequence-map prefix field | Weak: width alone is insufficient; mode 1 suppresses it, and match/mismatch can both emit value 2 | Establish mode and RF coding/position independently, then test predicted state changes on held-out visits |
| A six-coordinate stable group is the six-bit length field | Weak: that field exists only in the long prefix and is split across bytes | A verified long-form mapping must explain all six bits jointly, including byte-boundary behavior |
| A universal stable coordinate is a fixed prefix bit | Possible only as a structural hypothesis | It must survive a known RF bit-order/polarity/coding transform; current stable signs alone do not provide that transform |
| The known 60-word vocabulary is literally the two-bit prefix field | Incompatible as a one-to-one uncoded field mapping | A two-bit value has at most four values, and mode 1 carries none of these state bits; additional coding/state would need independent evidence |

No RF bit window was scanned based solely on these field widths. The measured
word-distribution dendrogram's tie sensitivity further weakens assigning software
enums to its apparent branch counts. These constraints narrow interpretations;
they do not establish that any observed cluster corresponds to a firmware field.

## Reproduction, tests and harness correction

```sh
uv run --no-project --with unicorn --with pyelftools python reports/2026_09_29_firmware_cluster_reaudit/prefix_execution.py
uv run --no-project --with unicorn --with pyelftools --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit/test_prefix_execution.py
```

The binary hash is checked before execution; the result records that hash and
the script hash in ignored `local/prefix-execution.json`. The fresh disassembly
is retained in `local/raw-audit.json`. Firmware accesses occur only in emulated
memory. No dish operation, RF collection or raw-data mutation occurs.

During harness development, reusing a translated Unicorn writer block bypassed
a newly installed stop boundary, allowing execution beyond the intended prefix
slice. The harness now invalidates the translation cache, hooks the writer entry
and asserts its final PC. A regression test first runs the writer, then checks
that prefix execution stops before it and leaves the writer context unchanged.
The final 1,120 assertions and regression test pass. These are isolated execution
checks, not a full scheduler-to-hardware execution or proof of on-air semantics.
