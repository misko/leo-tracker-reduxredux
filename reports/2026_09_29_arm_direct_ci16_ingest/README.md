# Direct stride-aware CI16 ingestion

This isolated Wave5 prototype adds `leo_full_search_run_ci16(workspace,
samples, scalar_stride, count, result)`.  It accepts a synchronous view into
packed or interleaved receiver data, converts each signed component exactly to
FP64 with `ldexp(value, -15)`, and writes the final presence workspace once.
The fused runner passes a receiver/window pointer with scalar stride four, so
it no longer allocates or fills a temporary complex array and `ingest()` no
longer scans and copies that array a second time.

The existing public `leo_full_search_run` complex-sample entry point and its
finite/range/error behavior are unchanged.  The new entry point rejects null
inputs, strides below two, non-nearest rounding mode, short counts, and counts
larger than the workspace.  CI16 itself is always finite and bounded.

Owned host and sanitizer tests cover all four rates, scalar strides two and
four, full-scale extrema at both ends, a non-frame-aligned logical tail, short
and overlong counts, exact `/32768` workspace values, and exact candidate
objects against the original entry point fed the same normalized values.  The
ARM unit is cross-built but was not executed.

`host704-v2` is the authoritative full-cohort parity receipt.  It reproduces
all 86,439 emitted candidate objects across 704 dwells and 15,488 windows with
zero changed candidates or windows versus sealed Wave5.  `host704` is the
earlier parity run made before the tail case was added to the build receipt;
its binary is identical, but `host704-v2` binds the final tests and sources.

Target commands for root-owned execution are:

```sh
./test_direct_ci16_ingest_arm
./fused_rate_coarse_gate_arm RATE EXACT CONTROL INPUT_CI16
```

The target fused binary SHA-256 is
`59b1c1086573dc8496d43c4d92e540186d0558c37aab27b46572cfe6cc9874e3`;
the target unit SHA-256 is
`e4747b61c356cfcd173cf277f1b48dce8945b724714848b04d66f46897106868`.
No ARM timing or speed claim is made here.

## V3 raw-value correction

The version above is retained as sealed v2 evidence, but its `/32768` scaling
does not match the fused Wave5 wrapper: that wrapper supplied raw integer-valued
doubles, and the coarse FP32 path already applies its own fixed scale.  Although
v2 happened to preserve all final candidates through scale invariance, it
changed internal sample semantics and used unnecessary `ldexp` calls.

`sources-v3`, `builds-v3`, and `host704-v3` are the corrected variant.  V3
converts signed CI16 directly to raw integer-valued FP64 and proves bit equality
of every workspace sample against the unchanged public entry point.  It also
rejects any `count`/`scalar_stride` combination whose final real/imaginary
scalar index would overflow `size_t`.  Its owned test uses sparse representative
regions including epoch zero, the midpoint, and the final two epochs, while
still checking every ingested sample and a non-frame-aligned input tail.

V3 again reproduces all 86,439 Wave5 candidate objects over 704 dwells with
zero changed candidates or windows.  The corrected ARM fused binary is
`e2bdbce32a45640fc60e634b255c1fa05ebaa8898f62b9b6d05046e0bcd5ea46`;
the ARM unit is
`13fc21a78ea18a8ce7efd7d22f6e47b05ea637a05a42c315b132e8aa32e860d3`.
Use `builds-v3/arm/build-receipt.json` for target execution.
