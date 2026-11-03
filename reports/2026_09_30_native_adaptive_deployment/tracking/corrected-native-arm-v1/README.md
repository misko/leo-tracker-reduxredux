# Fresh-native DS9 observations on ARM tracking

The qualified sidecar production tracker processed all 11,747 observations
from the corrected native detector's full host DS9 replay. Physical ARM output
is byte-identical to the corresponding host export: 64 tracks, output SHA-256
`584a06dd8e0cc9d7d2b39eda2bd188ac9802530c3305095aa1cb58e6ca23c5e1`.

The serial, cold CLI invocation took 22.023455 seconds wall, 22.021091 seconds
CPU, and 22,980 KiB peak RSS. It exited zero. This measures whole-history
tracking, not per-dwell processing or warm publication latency.

The deployed test executable was
`/mnt/glrtbench/native-adaptive/tests/sidecar-production-v1/leo-tracking`, SHA-256
`4358704575257c74e3dedbc1f40d1632d47630cb45fc438982aa1c16382ece0c`.
Its build and source qualification are in `../sidecar-production-v1/`.
The input was copied to
`/mnt/glrtbench/native-adaptive/tests/corrected-native-tracking-v1/candidates.tsv`.
`installed-sha256.txt` records both device hashes. The run used the existing
`measure-run` wrapper with a 120-second deadline and the input path as the
tracker's sole argument. No other analysis benchmark ran concurrently.

Run `python3 compare.py` to regenerate the exact-output comparison against
`../../ds9/corrected-full-replay-v1/full-public-c3-c4/tracks.tsv`.
These are freshly computed native observations, rather than persisted server
candidate values. Detection and projection ran on the host before this test;
neither detection nor location scoring executed on ARM in this invocation.
No RF was collected, production configuration was not changed, and continuous
real-time operation is not qualified by this result.
