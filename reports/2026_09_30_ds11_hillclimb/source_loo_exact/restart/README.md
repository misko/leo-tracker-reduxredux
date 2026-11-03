# Same-solver restart did not recover the failed fold

The separately declared one-restart diagnostic failed. Reconstructed objective
and gradient match the saved index-4 t8/NORAD-65855 endpoint. A fresh L-BFGS-B
invocation takes 19 evaluations and zero iterations, returns `ABNORMAL:` and
`success=false`, and leaves position, timing, retained score and common held
score exactly unchanged. Its maximum gradient remains 3.5713846e-5 and its
finite-difference audit discrepancy remains 1.9392350e-6.

The process completed normally in 9.22 seconds under a 90-second cap with one
BLAS thread. Seven eligibility tests pass. No reference-position error was
used. The [protocol](PROTOCOL.md), [result](result.json), [receipt](receipt.json)
and original failed screen remain separate and preserved. No further
same-solver restart is justified by this experiment.
