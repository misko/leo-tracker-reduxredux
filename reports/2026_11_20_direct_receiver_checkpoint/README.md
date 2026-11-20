# Direct receiver research checkpoint

The [working copy patch](paused-work.patch) preserves the unfinished direct detector, compact clock, orbit-geometry and field-input experiments that followed the standalone C receiver study. It includes the draft implementation, test edits, trial protocols and the local changes to worker supervision. These experiments were paused before receiver qualification. The [completed study](../2026_11_19_receiver_screening/native-receiver/README.md) and [algorithm guide](../../algorithms.md) identify the measured implementations.

The patch is relative to the published benchmark source in this checkout. To inspect it or resume the drafts in a separate checkout based on this publication, run from the repository root.

```sh
patch=reports/2026_11_20_direct_receiver_checkpoint/paused-work.patch
git apply --stat "$patch"
git apply --check "$patch"
git apply "$patch"
```
