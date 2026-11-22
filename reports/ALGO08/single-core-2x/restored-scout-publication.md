# Packed cancellation with original carrier refinement

The first matched pair reached **2.014× elapsed** on DS30-0374, from 132.90 to 66.00 s. CPU fell from 126.83 to 64.70 s, **1.960×**. All 4,157 selected carrier frequencies, epochs and ranks matched. Both positions agreed within 0.052 mm and both arms retained every deployed observation owner. Both publications contained the eight required PNGs. Seven decoded images matched. The position plot, grid digest and path digest differed. Both arms began with all 106 compressed files cached and registered zero filesystem input blocks. [First-pair artifact audit](measurements/restored-scout-0374-audit.json)

## Second physical assignment

The first recording crossed the 2× elapsed target and recovered all measured frequencies. DS30-0008 is next in the original order and is the one recording where the earlier receiver degraded both position estimates by about 19 m. Its corrected scout was verified on the three affected visits. A metadata-only check found all 1,997,612 pages of its 106 compressed input files resident. Run this one full matched comparison, deployment first. Check whether all 7,016 frequencies and epochs and the two complete position fits survive the real receiver path. Record elapsed and CPU speed separately, all PNGs, owner maps and cache status. Review the first two assignments together before opening another recording.

## First physical assignment

The three changed fractional carrier measurements on DS30-0008 appeared when the compiler used profile feedback on the delay-product kernel. Rebuilding that single object without feedback restored the three original epoch and frequency measurements. The change applies to every scan. It has no location input, threshold or satellite selection. The rest of the receiver retains packed cancellation and its existing compiler settings. Replacing the three measurements in a saved solver replay restored all deployed assignments and both coordinates within 0.027 mm. [Dense crossover](screened-graph-transfer.md) · [Frozen integration](measurements/restored-scout-graph-freeze.json)

Run one raw pair on DS30-0374, the first recording in the original four-case order, after checking the corrected receiver on the previously archived weak-carrier and Austin controls. A new lost or gained factor on those controls sends the change back to saved-sample triage. Use the ordinary one-core benchmark with the candidate first, fresh output roots, the exact capture-time orbit archive and cache snapshots before both arms. The scientific check compares all selected measurements, both positions and owner maps, grids, paths and decoded PNGs. Record wall time, CPU time, filesystem input blocks and the three publication stages. A metadata-only preflight observed all 2,054,132 compressed pages already resident across 106 physical input files.

The previous guarded receiver and solver needed 3.80 elapsed seconds and 2.11 CPU seconds beyond half-time on this recording. The separate graph and cancellation trials made that gap small enough to measure end to end. They do not establish an additive improvement. Review this single pair before scheduling any further roof recording. The known Indian omission and northern near-face uncertainty remain open.

The restored receiver passed the two saved-sample checks. Returned ranks, timing and frequencies matched deployment on all 74 factors from the DS26 weak-carrier and Austin controls. All 52 continuation results matched. On 36 weak-carrier lanes the restored receiver used 2.49% more CPU than the packed version and ran 2.70× faster than deployment. Austin's two measured windows came from the same antenna and assess receiver transfer. They do not supply a physical position accuracy result. [Wrapped-refinement attribution](receiver-cfo-lineage.md) · [Receiver cost and Austin controls](receiver-cfo-native.md)

## Reproduction

The following commands use the reviewed Gauss bundle paths, service account and release. The specification includes absolute library paths. Recreating it byte for byte requires the listed destination. The freezer requires an empty destination and an unused receipt filename. The one-case runner can use a fresh workspace with the existing verified bundle.

```sh
bench=/tmp/leo-algo08v2-2x-bench
build="$bench/integration-restored-scout-graph"
work=/tmp/ds30-v2-stage-restored-scout-ad417a
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
PYTHONPATH=.:src "$release/venv/bin/python" -BPs -m reports.ALGO08.single-core-2x.freeze_packed_graph \
  "$bench/integration-packed-graph" "$bench/receiver-cfo-lineage-fix/restored.so" "$build" \
  "$bench/restored-scout-freeze.json" --restored-scout-build "$bench/receiver-cfo-lineage-fix/build.json"
stage() {
  action=$1
  shift
  sudo -n -u leo -- env PYTHONPATH="$PWD:$PWD/src:$release" OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 "$release/venv/bin/python" -BPs \
    -m reports.ALGO08.single-core-2x.ds30_stage "$action" "$work" \
    "$build/reports/ALGO08/single-core-2x/run-candidate" "$build/spec.json" \
    ad417aaa51a49edf1a36aca571683bbc0479317c06b821030373656461a28acd "$@"
}
stage run --case DS30-0374 --cache-library "$bench/ds30-cache-residency.so"
stage score
```
