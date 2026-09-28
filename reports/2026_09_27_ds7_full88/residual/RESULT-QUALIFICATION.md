# Fixed-prediction residual audit qualification

The prescribed all-88 fixed-prediction residual audit did not produce a result file. The one permitted attempt exited with status 1 after 60.31 seconds, below its 300-second wall cap and its 8 GiB address-space limit. Its maximum resident set was 5,977,144 KiB. No audit process remained afterward, and no retry was run.

The required independent response index has 88 records and retains `single-062`. That source response is converged but has `boundary_hit: true`. The unchanged audit program requires every independent source passed to `response_x` to have `boundary_hit: false`, raising `ValueError: audit requires a qualified frozen estimate` otherwise. Thus the prescribed requirement to include the boundary record conflicts with this program's qualified-estimate precondition. The terminal receipt binds the source index, joint response, run seal, program, resource report, and `single-062` source receipt.

No fixed-prediction residual comparisons, RMS summaries, or diagnostic qualification are available from this attempt. This failed audit supplies no geographic result and must not be represented as a residual validation of the joint prediction.
