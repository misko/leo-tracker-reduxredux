# Conditional final-member preparation continuation

The original group11 preparation lease remains capped at 1,200 seconds. At
the seventh completed bank it had approximately 63 seconds left, shorter than
the measured export-plus-bank workloads. Its final operation must stop at that
deadline and retain any incomplete artifacts; this document does not extend a
running timeout or erase its outcome.

If recording 088 is unavailable when that controller terminates, complete only
that member in a separate bounded lease: at most 330 seconds total, at most
90 seconds for a missing export, and at most 240 seconds for a new bank.
Reuse an already complete source-bound export. Write any retry bank under
`.leo/ds7-wave3/baseline-completion/`, never overwrite partial output. Keep the
unchanged original exporter, candidate policy, masks and scientific parameters.
Stop on another timeout or validation failure. Publish a new immutable all16
ready index only if all original first-eight and final-eight members validate.

This resource decision uses observed preparation runtimes, not positioning
scores. It supplies the already declared group11 comparison; it does not select
different recordings or models. One CPU/BLAS thread, nice 19, no IQ/new RF,
read-only source access. Source reads remain serialized. The separately bounded
combined-export equivalence benchmark may use its slot after the original
controller stops, before this completion lease begins.
