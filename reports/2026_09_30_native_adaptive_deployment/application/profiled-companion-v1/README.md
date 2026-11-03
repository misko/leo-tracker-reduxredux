# Profiled live companion v1

This directory qualifies the separate opt-in `leo-adaptive-live-server-compat`
application. The existing portable executable and its persisted v4 schemas are
unchanged. The companion emits
`leo-native-live-profiled-capabilities/v1` and
`leo-native-live-profiled-summary/v1`, and reports the exact support profile
name and manifest digest.

`qualification.json` binds the frozen source, host and ASAN/UBSAN lifecycle
tests, ARM cross-build, capability output, dependency archives, and the
replaceable LGPL support DSO package. The fake lifecycle tests cover portable
v4 regressions, successful profiled derivation, unavailable and invalid
derivation failures, malformed profile metadata, cleanup, and the requirement
that a qualified run accept at least one candidate.

`deployment.json` and `physical-arm/` contain the root-run physical CPU test
and installation evidence. The companion is installed at
`/mnt/glrtbench/native-adaptive/applications/8f8a1fa2b871c97b` on
`192.168.1.15`. The `live-current` symlink still selects the portable
application. No RF capture or autostart occurred.

The sibling `../profiled-analysis-v1/` evidence runs all 24,681 recorded DS9
candidate rows through the real support profile and `Analysis`, deriving
11,747 observations and reconstructing 64 tracks with zero queue loss. Its
physical paced run used an independent producer and background analysis owner;
it is a recorded-data composition proof, not a five-second freshness or live
RF qualification.

Strict full-pipeline parity remains false. Six known C4 duplicate-rank identity
ties remain outside this support-profile integration. Measured source-progress
age also stops advancing when recorded input ends, so it must be read together
with snapshot-result duration and post-stop drain time.
