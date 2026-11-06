# Interrupted restored-runtime test attempt

The first broad restored-runtime test process (exec session 45143) terminated
with exit code 143 after showing progress beyond 95%. It produced no completed
pytest summary and is not counted as a passing suite. No assertion failure was
reported before termination. The reason for SIGTERM is not established.

The observer tests are checked separately, and the full suite is rerun in its
own session. A later passing receipt does not turn this interrupted attempt into
a pass. The candidate's earlier complete 2,027-test receipt remains separate.

The first session-isolated retry used `setsid` without its wait option. The
launcher exited before pytest, its output pipe closed, and pytest recorded
`BrokenPipeError` ([receipt](restored-detached-error.xml)). This was a test-launch
error, not a scientific assertion failure. After confirming that process had
exited, the retry uses `setsid --wait` with a persistent log file. The four new
observer tests independently pass in `observer-tests.xml`.
