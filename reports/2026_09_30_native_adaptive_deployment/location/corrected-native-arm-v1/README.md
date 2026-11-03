# Fresh-native fixed-site location scoring on ARM

The same-source host and physical PLUTO+ executables produce byte-identical
JSON for both registered sites in the corrected native DS9 location fixture.
All 64 tracks match at each site, including every selected satellite, time
offset, fitted offset and held-out/fit residual. Scores are
226.7107329749787 and 412.74249165571746 Hz. The output SHA-256 is
`c75aafa9872db1d3ad96e3f1c0507a4471801a9b2d9eb5db53364ffa1f65cc3d`.

With two scoring workers, the ARM whole process takes 16.697897 seconds wall,
30.673231 seconds CPU and 24,300 KiB peak RSS, exiting zero. This includes
fixture parsing and both site scores; it is not an isolated per-site timer.
The ARM component test also passes. Host build runs its component tests.

Both binaries were built from the unchanged sources recorded in
`source-manifest.json` using `native/adaptive/location/build.sh`, host and arm
modes. Executables are retained under `artifacts/`. Device executable and
fixture hashes are in `installed-sha256.txt` and were checked against local
artifacts after execution. The isolated device directory is
`/mnt/glrtbench/native-adaptive/tests/corrected-native-location-v1/`.
The command was `measure-run 120 leo-location score native-e2.loc1 2`, with
absolute paths in that directory and the existing measurement wrapper.

The fixture comes from
`../../ds9/corrected-full-replay-v1/full-public-c3-c4/native-e2.loc1`: fresh
native detection/tracking on the host, with saved reference orbit states and
registered sites. This execution does not rebuild the orbit catalogue, run
detection, perform a regional search, or collect RF. The existing native/server
partition differences remain; identical host/ARM scores do not establish
server equivalence or continuous real-time qualification.

Run `python3 test_compare.py` and `python3 compare.py` in this directory to
check the finite-value/structure comparator and reproduce `comparison.json`.
The comparator requires exact identities/time offsets and at most 1e-6 Hz
numeric differences; this run has zero numeric difference and identical bytes.
