# Named server-authority support compatibility

This optional module reproduces the frozen server support arithmetic and Python
decimal authority for one explicitly bound profile. The portable runtime
remains the default. Nothing in this directory changes pipeline-v1 persisted
contracts, live ingestion, or online authority selection.

`SupportDeriver` is single-owner and synchronous. Its constructor requires the
exact profile name and `profile.json` digest. It returns numeric support and all
four decimal moment lexemes from one call, preventing arithmetic and authority
spelling from diverging. It owns one exact successful cache entry; failed calls
do not replace it. Independent instances may run concurrently.

The environment must already use round-to-nearest and C numeric decimal
conventions. Construction and calls check these conditions and fail without
changing the process locale or floating-point environment.

`libleo-server-pow3-fma.so` exposes only `leo_server_pow3_fma`. It directly
calls the renamed glibc 2.43 FMA pow core with exponent 3. It does not export or
interpose `pow`, and no `LD_PRELOAD` or runtime symbol lookup is used. The
compatibility calculation uses this entry only for moment3. The default runtime
does not link this library.

The derived glibc files retain their notices and are covered by
LGPL-2.1-or-later in `glibc/COPYING.LIB`. The DSO is separately replaceable;
the complete corresponding source, build script, and object-producing commands
are retained here for relinking.

Any package containing the optional pow3 DSO must also contain the LGPL notice,
this corresponding source directory, the build script, and the relinking
instructions. A binary-only application package is insufficient.

Run `./build.sh host` and `./test.sh host`. The tests cover the frozen DS9
corpus, the deterministic 116,364-value Python-repr adversarial corpus, exact
cache lifecycle and failure behavior, the unchanged portable support bits, and
the exported-symbol boundary. `sanitize` and `arm` are explicit build modes;
ARM tests run through QEMU unless copied to the target for a CPU-only run.

Physical ARM component testing reproduced all DS9 and adversarial values. The
full DS9 verifier took 92.132 seconds. A derive-only 1,024-candidate prefix
measured uncached calls at 9.547 ms mean, 10.119 ms p95, and 10.809 ms maximum;
cache hits averaged 4.239 us. This module is therefore compatibility evidence,
not an integrated real-time qualification. The proposed session-bound port and
its callback placement are recorded in
`reports/2026_09_30_native_adaptive_deployment/runtime/server-authority-compatibility-session-integration.md`.
