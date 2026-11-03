# Portable application regression after deferred Session support

The corrected source closure
`/var/tmp/leo-support-deferred-source-release.JarVoz` passes host live Analysis
and fake-provider CLI tests with the portable profile unchanged. Compiler and
test scratch use `/var/tmp` because the user quota on `/tmp` was exhausted.
The CLI fixture writer now checks failed writes explicitly.

The full saved-event replay with two analysis workers accepts 11,747
observations, reconstructs 64 tracks, drops no queued events, and reproduces
weighted MSE 64906.771460780015 exactly on the host. This uses the same
`full-pinned-coalesced` policy and 0.01 replay scale as the prior application
regression. It qualifies portable composition only: no IQ detection, RF,
five-second continuous freshness or optional profile selection is claimed.

This evidence precedes the separate optional support-port addition to the live
Analysis API. The frozen generic source is archived with the
[physical deferred-stage evidence](../../runtime/session-deferred-physical-v1/receipt.json).
