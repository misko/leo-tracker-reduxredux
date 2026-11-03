# Background catalogue scoring during local capture

This benchmark runs one location worker against the complete DS9 native-track
fixture while the scanner owns local PLUTO+ capture. It measures CPU contention;
the scorer does not consume the current live candidates.

The exact command, release ID, host monotonic intervals, whole-process wall/CPU
time and peak RSS are in `receipt.json`. Every result is compared as parsed JSON
against `../../location/complete-scan-native-arm-score.json`, including every
point score, track winner, fitted value and selected time offset. Input fixture
SHA-256 is `f55517a03696d56b952ed0027268c5f9d65c871b68581a53efc5552ee48cde50`.

The scanner runs at normal priority. The scorer command is prefixed with
`nice -n 19`; the wrapper and its scorer child inherit that priority. The actual
process priorities were read from `/proc/PID/stat` and preserved in
`priority-observation.json`. Neither process is pinned to a specific CPU.

Scoring calls are admitted for at most 480 seconds, each with a 75-second hard
watchdog and a maximum of 16 calls. The RF process has its own independent
585-second requested duration and 600-second external bound. Scoring creates
no additional RF collection. Per-call outputs remain available as numbered
JSON/stderr files; exact-match checks do not imply server scientific parity.
