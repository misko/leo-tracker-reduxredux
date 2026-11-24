# CI16 byte planes save payload space and cost first-read CPU

On the verified first original DS30-0169 member, high-byte-plane Zstandard
reduced the payload from **76.800 MB** with existing aperture packing to
**69.107 MB**. Its writer and complete authenticated readback took
**320.2–320.8 CPU ms**, compared with **184.2–185.7 ms** for aperture
packing. LZ4 took **277.3–277.5 CPU ms** and produced a larger payload.
All formats recovered the original CI16 bytes exactly. Neither new
codec met the frozen first-use gate. [Protocol](ci16-planes-protocol.md) · [Receipt](measurements/ci16-planes-0169.json)

## Same owned physical input and full verification

The assay used the one already-resident original member and bound its
manifest, signed index, encoded digest, decoded whole-member digest and
all 64 ordered decoded window digests. The ordinary writer emitted the
exact released **78,852,856-byte** level-1 Zstandard member. All formats
recovered **102,400,000 original bytes** through complete first
readback, including the 13 originally excluded visits. The split
layouts keep independently decodable 80,000- and 120,000-sample blocks
per stereo visit. Each signed sample remains in its original ordinal
and little-endian wire representation after decode.

The transform keeps the four low bytes in chronological sample order and
passes only the four contiguous high planes to one conventional fast
codec. The physical packing comparator used the established native
SSSE3 codec. All 128 parts used width 12 and shift 0 in both runs.
The standard independent-frame control used the same level-1 Zstandard
codec with an unmodified sample layout. The trial table binds the
original manifest and index and commits exact encoded bytes and every
original decoded extent. The reader verified the table pin, all encoded
bytes and all decoded commitments before returning a complete result.
Separate byte comparisons checked each recovered extent against the
owned originals. Their 10–14 CPU ms per complete pass are recorded
separately from the table's writer and reader clocks.

| Layout | Payload MB | Writer CPU ms, forward / reverse | Complete verified read CPU ms | Writer + complete read CPU ms | Ready 20/8 verified read CPU ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original level-1 stream | 78.853 | 168.691 / 168.985 | 138.760 / 138.029 | 307.452 / 307.014 | 137.555 / 137.347 |
| Established width packing | 76.800 | 103.764 / 102.711 | 81.969 / 81.521 | **185.733 / 184.231** | **31.197 / 31.315** |
| Independent level-1 Zstandard blocks | 78.854 | 156.010 / 155.660 | 139.365 / 140.318 | 295.374 / 295.978 | 55.150 / 54.904 |
| High planes with LZ4 | 83.452 | 185.020 / 185.615 | 92.524 / 91.664 | 277.544 / 277.280 | 37.173 / 37.706 |
| High planes with level-1 Zstandard | **69.107** | 216.352 / 215.457 | 104.414 / 104.732 | 320.766 / 320.190 | 39.513 / 39.352 |

The 20/8 read paid authentication on every encoded part, including
unrequested tails. It recovered **40,320,000 bytes** from the eight
admitted full anchors and 43 admitted short visits. The original
whole-member comparator recovered the complete member on each read.
Table sizes were 5,648 bytes for the ordinary stream and
23,872–23,877 bytes for the split layouts. The trial kept the waveform
representations in memory, recorded **384 MiB** peak RSS and wrote
52 KiB of build and receipt files in tmpfs. Gauss ran on CPU 2,
nice 15 and I/O priority 7 under the shared lock. There was no detector,
solver, capture, alternate durable writer or original archive read.
The writer and reader clocks include transformation, output allocation,
codec work, digest work and table construction or validation.

Reusing an existing original file adds an observed **168.584 CPU ms and
170.549 elapsed ms** to admit its owned bytes through the installed
ordinary decoder and all original checks. That conversion was performed
once before either benchmark order. It is separate from the writer and
readback clocks. No new byte-plane representation can be read directly
by the installed original-stream reader. Its migration would need the
verified conversion and the measured new write plus readback, as well
as durable output costs. The previous durable member study remains the
comparison that includes storage and signed detection. [Existing packed first use](eight-first-use-held.md)

## Size and decode-speed trade

The held entropy test trained four pairs of independent low/high
histograms on eight evenly spaced visits. It scored eight disjoint
offset visits with the resulting probabilities. The low bytes used
8.000 held bits and the highs used 2.415–2.570 bits per component.
Applied to this member, an ideal coder for those marginals would emit
**67.151 MB** with zero container overhead. This is a model-specific
estimate. It allows neither extra temporal context nor coding overhead.
Replacing samples with per-visit modular first differences made this
held estimate **69.531 MB**. On those observed marginals, the actual
69.107 MB high-plane Zstandard payload leaves about 2 MB of entropy
coding headroom. An ideal 67.151 MB payload could save only about
15% of original payload transfer time at fixed bandwidth.

For ready reads, high-plane Zstandard saved **7.693 MB** and cost
**8.04–8.32 CPU ms** more per member than width packing. If all
encoded bytes had to cross a cold link serially, the model breaks even
at **925–957 MB/s**. At the previously modeled 207.5 MB/s link rate
for DS30-0169, this is roughly **29 ms of net modeled ready-read
saving** per member. The first-use CPU penalty was **135–136 ms**.
Even crediting the saved 7.693 MB to both output writing and independent
readback, and charging no other format work, first use would break even
near **113–114 MB/s** in that serial model. The actual comparison was
resident. Cold I/O and overlapping writer or reader work can change
these bounds. [Earlier DS30-0169 acquisition budget](receiver-ceiling-0169.md)

## Reproduction

Use the exact installed storage release, the shared Gauss lock and a
fresh output directory under tmpfs. The runner checks original member
residency and exact input custody before the stock decoder is allowed
to open the member. The as-run receipt SHA-256 is
`ccc89c046affd699b5fe9c319c9bb654bc226e7c792624e432b5f667d9560457`.
Four component tests cover both codecs, unaligned wire bytes and all
16-bit signed patterns, truncated encodings, wrong originals, changed
table and changed unused tails during a ready read.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
  PYTHONPATH="$release/src:$PWD:$PWD/reports/ALGO08/v3:$release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.ci16_planes_trial "$new_tmpfs_output"
```
