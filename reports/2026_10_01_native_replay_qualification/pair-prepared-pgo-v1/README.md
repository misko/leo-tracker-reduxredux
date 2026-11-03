# Prepared pair bound: fresh PGO qualification

The private bound-subset preparation now computes a conservative reciprocal
once per track. It is used only for candidate rejection; uncertain candidates
continue to the unchanged full scorer. Published contracts are unchanged.

The fresh profile uses four training sites and sixteen disjoint evaluation
sites from the existing protocol. Source hashes, source snapshots, profile,
build log, verified device payload hashes and ARM unit receipts are retained.
Evaluation runs in control/new/new/control order against the qualified
prevalidated-stencil PGO build. Mean CPU is 12.237275 versus 12.188854 seconds;
all scores match exactly. The ordinary-build experiment and host full-trace
comparisons are in `../pair-prepared-v1/`.

Full physical ARM search and selected-site association results are in
`../regional-arm-pair-prepared-v1/`. All 400 search evaluations and association
results equal the previous ARM control. Search passes the independent host
1e-9 Hz comparison and full associations equal host. Search consumes
297.358715 CPU seconds in 158.115778 wall seconds; associations consume
3.264946 CPU seconds in 2.154077 wall seconds. This small isolated improvement
does not qualify continuous concurrent processing.
