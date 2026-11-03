# Output serialization repair before the complete batch

The initial DS7 early child finished its numerical work but failed serializing
a NumPy int64 active-bound count. It exited 1, produced no result JSON and yielded
no scored geographic outcome. The writer now explicitly converts the count to
Python int and the audit flag/difference to bool/float. No objective, start,
bound, optimizer or qualification threshold changes.

This is an administrative rerun after an output failure, an explicit exception
to the original no-retry execution rule. The full nine-panel batch will run with
the corrected writer; initial DS7 early is not counted as a completed scientific
result or as success within the original first attempt. Preserve this failure
in reporting. Any timeout or numerical failure of the corrected batch remains
a failure without automatic retry.
