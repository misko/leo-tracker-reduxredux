# ARM execution provenance

All scientific calls use the unchanged, hash-verified `arm-goal40mag` binary
from the earlier RAM experiment. No RF collection is involved.

`arm` is a failed staging attempt: this device's BusyBox tar has no `-z`
option. No detector calls from that attempt enter the comparison. The error
and incomplete receipt are retained.

`arm02` successfully ran the first eight capture batches: 64 unique dwells.
It was deliberately interrupted while compressing the next archive on the
host, with no ARM detector executing. Its exact running source is saved as
`arm02/runner-source.py`. Those 64 results are retained as an explicit prefix.

`arm03` validates that prefix against its raw phase outputs, source contexts,
plan hash, and ARM binary hash, then executes the remaining 640 dwells. Its
combined rows contain each of the planned 704 cases exactly once. Its final
receipt binds the prefix receipts and the completed combined output.

The latter transport serves one owned archive at a time over a temporary HTTP
listener bound to the host's development-LAN address. Only the PLUTO+ address
can fetch it. The target extracts to its unique SD staging directory and
verifies every raw IQ/template hash before invoking the detector. The
listener closes after the transfer; it never serves the source corpus or
arbitrary host paths. SSH is still used for command execution. Transfers and
file validation occur before the timed detector calls.

Temporary host archives and exported raw copies from the aborted attempts
were removed after retaining their receipts. The sealed NPY input corpus,
source recordings, and all completed scientific results remain intact.
Target-side staging is retained for reproduction.
